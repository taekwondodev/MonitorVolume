#include "MonitorTransport.h"

#include <CoreFoundation/CoreFoundation.h>
#include <IOKit/IOKitLib.h>
#include <dlfcn.h>
#include <stdbool.h>
#include <string.h>
#include <unistd.h>

typedef CFTypeRef IOAVServiceRef;
typedef IOAVServiceRef (*MVCreateServiceFunction)(CFAllocatorRef allocator, io_service_t service);
typedef IOReturn (*MVReadI2CFunction)(
    IOAVServiceRef service,
    uint32_t chipAddress,
    uint32_t offset,
    void *outputBuffer,
    uint32_t outputBufferSize
);
typedef IOReturn (*MVWriteI2CFunction)(
    IOAVServiceRef service,
    uint32_t chipAddress,
    uint32_t dataAddress,
    void *inputBuffer,
    uint32_t inputBufferSize
);

typedef struct {
    void *handle;
    MVCreateServiceFunction createService;
    MVReadI2CFunction readI2C;
    MVWriteI2CFunction writeI2C;
} MVIOAVFunctions;

static bool MVLoadIOAVFunctions(MVIOAVFunctions *functions) {
    functions->handle = dlopen(
        "/System/Library/Frameworks/IOKit.framework/Versions/A/IOKit",
        RTLD_LAZY | RTLD_LOCAL
    );
    if (functions->handle == NULL) {
        return false;
    }
    functions->createService = (MVCreateServiceFunction)dlsym(
        functions->handle,
        "IOAVServiceCreateWithService"
    );
    functions->readI2C = (MVReadI2CFunction)dlsym(functions->handle, "IOAVServiceReadI2C");
    functions->writeI2C = (MVWriteI2CFunction)dlsym(functions->handle, "IOAVServiceWriteI2C");
    if (functions->createService == NULL || functions->readI2C == NULL || functions->writeI2C == NULL) {
        dlclose(functions->handle);
        return false;
    }
    return true;
}

static bool MVStringMatches(CFTypeRef value, const char *expected) {
    if (value == NULL || CFGetTypeID(value) != CFStringGetTypeID()) {
        return false;
    }
    CFStringRef expectedValue = CFStringCreateWithCString(
        kCFAllocatorDefault,
        expected,
        kCFStringEncodingUTF8
    );
    if (expectedValue == NULL) {
        return false;
    }
    bool matches = CFStringCompare((CFStringRef)value, expectedValue, 0) == kCFCompareEqualTo;
    CFRelease(expectedValue);
    return matches;
}

static bool MVCopyString(CFTypeRef value, char *output, uint32_t capacity) {
    if (value == NULL || CFGetTypeID(value) != CFStringGetTypeID() || capacity == 0) {
        return false;
    }
    return CFStringGetCString((CFStringRef)value, output, capacity, kCFStringEncodingUTF8);
}

static bool MVOutputNameMatches(CFTypeRef productNameValue, const char *outputName) {
    char productName[128] = {0};
    if (!MVCopyString(productNameValue, productName, sizeof(productName))) {
        return false;
    }
    if (strcmp(outputName, productName) == 0) {
        return true;
    }
    size_t outputLength = strlen(outputName);
    size_t productLength = strlen(productName);
    return outputLength > productLength
        && outputName[outputLength - productLength - 1] == ' '
        && strcmp(outputName + outputLength - productLength, productName) == 0;
}

static bool MVNumberMatches(CFTypeRef value, uint32_t expected) {
    if (value == NULL || CFGetTypeID(value) != CFNumberGetTypeID()) {
        return false;
    }
    uint32_t actual = 0;
    return CFNumberGetValue((CFNumberRef)value, kCFNumberSInt32Type, &actual) && actual == expected;
}

static bool MVFramebufferMatches(
    io_registry_entry_t framebuffer,
    const char *manufacturer,
    uint32_t productID,
    const char *serial
) {
    CFTypeRef attributesValue = IORegistryEntryCreateCFProperty(
        framebuffer,
        CFSTR("DisplayAttributes"),
        kCFAllocatorDefault,
        0
    );
    if (attributesValue == NULL || CFGetTypeID(attributesValue) != CFDictionaryGetTypeID()) {
        if (attributesValue != NULL) {
            CFRelease(attributesValue);
        }
        return false;
    }

    CFDictionaryRef attributes = (CFDictionaryRef)attributesValue;
    CFTypeRef productValue = CFDictionaryGetValue(attributes, CFSTR("ProductAttributes"));
    if (productValue == NULL || CFGetTypeID(productValue) != CFDictionaryGetTypeID()) {
        CFRelease(attributesValue);
        return false;
    }

    CFDictionaryRef product = (CFDictionaryRef)productValue;
    bool matches = MVStringMatches(CFDictionaryGetValue(product, CFSTR("ManufacturerID")), manufacturer)
        && MVNumberMatches(CFDictionaryGetValue(product, CFSTR("ProductID")), productID)
        && (serial == NULL
            || MVStringMatches(CFDictionaryGetValue(product, CFSTR("AlphanumericSerialNumber")), serial));
    CFRelease(attributesValue);
    return matches;
}

static bool MVFramebufferMatchesAudioDisplay(
    io_registry_entry_t framebuffer,
    const char *outputName,
    const char *manufacturer,
    uint32_t *productID,
    char *serial,
    uint32_t serialCapacity
) {
    CFTypeRef attributesValue = IORegistryEntryCreateCFProperty(
        framebuffer,
        CFSTR("DisplayAttributes"),
        kCFAllocatorDefault,
        0
    );
    if (attributesValue == NULL || CFGetTypeID(attributesValue) != CFDictionaryGetTypeID()) {
        if (attributesValue != NULL) {
            CFRelease(attributesValue);
        }
        return false;
    }
    CFTypeRef productValue = CFDictionaryGetValue((CFDictionaryRef)attributesValue, CFSTR("ProductAttributes"));
    if (productValue == NULL || CFGetTypeID(productValue) != CFDictionaryGetTypeID()) {
        CFRelease(attributesValue);
        return false;
    }
    CFDictionaryRef product = (CFDictionaryRef)productValue;
    CFTypeRef productIDValue = CFDictionaryGetValue(product, CFSTR("ProductID"));
    uint32_t resolvedProductID = 0;
    bool matches = MVStringMatches(CFDictionaryGetValue(product, CFSTR("ManufacturerID")), manufacturer)
        && MVOutputNameMatches(CFDictionaryGetValue(product, CFSTR("ProductName")), outputName)
        && productIDValue != NULL
        && CFGetTypeID(productIDValue) == CFNumberGetTypeID()
        && CFNumberGetValue((CFNumberRef)productIDValue, kCFNumberSInt32Type, &resolvedProductID);
    if (matches) {
        *productID = resolvedProductID;
        serial[0] = '\0';
        CFTypeRef serialValue = CFDictionaryGetValue(product, CFSTR("AlphanumericSerialNumber"));
        if (serialValue != NULL && CFGetTypeID(serialValue) == CFStringGetTypeID()) {
            MVCopyString(serialValue, serial, serialCapacity);
        }
    }
    CFRelease(attributesValue);
    return matches;
}

static bool MVIsExternalProxy(io_registry_entry_t entry) {
    if (!IOObjectConformsTo(entry, "DCPAVServiceProxy")) {
        return false;
    }
    CFTypeRef location = IORegistryEntryCreateCFProperty(
        entry,
        CFSTR("Location"),
        kCFAllocatorDefault,
        0
    );
    bool external = MVStringMatches(location, "External");
    if (location != NULL) {
        CFRelease(location);
    }
    return external;
}

static uint8_t MVChecksum(const uint8_t *bytes, uint32_t count, uint8_t initial) {
    uint8_t checksum = initial;
    for (uint32_t index = 0; index < count; index += 1) {
        checksum ^= bytes[index];
    }
    return checksum;
}

static MVDDCStatus MVReadVCP(
    MVIOAVFunctions functions,
    IOAVServiceRef service,
    uint8_t code,
    uint16_t *current,
    uint16_t *maximum
) {
    uint8_t request[] = {0x82, 0x01, code, 0x00};
    request[3] = MVChecksum(request, 3, 0x6E);

    IOReturn writeStatus = functions.writeI2C(service, 0x37, 0x51, request, sizeof(request));
    if (writeStatus != kIOReturnSuccess) {
        return MVDDCStatusReadFailure;
    }
    usleep(10000);
    writeStatus = functions.writeI2C(service, 0x37, 0x51, request, sizeof(request));
    if (writeStatus != kIOReturnSuccess) {
        return MVDDCStatusReadFailure;
    }

    bool receivedMalformedResponse = false;
    for (uint32_t attempt = 0; attempt < 5; attempt += 1) {
        usleep(50000);
        uint8_t reply[11] = {0};
        IOReturn readStatus = functions.readI2C(service, 0x37, 0x51, reply, sizeof(reply));
        if (readStatus != kIOReturnSuccess) {
            continue;
        }
        bool hasData = false;
        for (uint32_t index = 0; index < sizeof(reply); index += 1) {
            hasData = hasData || reply[index] != 0;
        }
        if (!hasData) {
            continue;
        }
        if (reply[0] != 0x6E
            || reply[1] != 0x88
            || reply[2] != 0x02
            || reply[4] != code
            || MVChecksum(reply, 10, 0x50) != reply[10]) {
            receivedMalformedResponse = true;
            continue;
        }
        if (reply[3] == 0x01) {
            return MVDDCStatusUnsupported;
        }
        if (reply[3] != 0x00) {
            receivedMalformedResponse = true;
            continue;
        }
        *maximum = (uint16_t)((reply[6] << 8) | reply[7]);
        *current = (uint16_t)((reply[8] << 8) | reply[9]);
        return MVDDCStatusSuccess;
    }
    return receivedMalformedResponse ? MVDDCStatusMalformedResponse : MVDDCStatusReadFailure;
}

static MVDDCStatus MVCreateTargetService(
    MVIOAVFunctions functions,
    const char *manufacturer,
    uint32_t productID,
    const char *serial,
    IOAVServiceRef *targetService
) {
    io_iterator_t iterator = IO_OBJECT_NULL;
    kern_return_t iteratorStatus = IORegistryCreateIterator(
        kIOMainPortDefault,
        kIOServicePlane,
        kIORegistryIterateRecursively,
        &iterator
    );
    if (iteratorStatus != KERN_SUCCESS) {
        return MVDDCStatusReadFailure;
    }

    MVDDCStatus status = MVDDCStatusTargetUnavailable;
    bool targetFramebuffer = false;
    io_registry_entry_t entry = IO_OBJECT_NULL;
    while ((entry = IOIteratorNext(iterator)) != IO_OBJECT_NULL) {
        if (IOObjectConformsTo(entry, "AppleCLCD2") || IOObjectConformsTo(entry, "IOMobileFramebufferShim")) {
            targetFramebuffer = MVFramebufferMatches(entry, manufacturer, productID, serial);
        } else if (targetFramebuffer && MVIsExternalProxy(entry)) {
            *targetService = functions.createService(kCFAllocatorDefault, entry);
            status = *targetService == NULL ? MVDDCStatusReadFailure : MVDDCStatusSuccess;
            IOObjectRelease(entry);
            break;
        }
        IOObjectRelease(entry);
    }

    IOObjectRelease(iterator);
    return status;
}

MVDDCStatus MVDDCResolveAudioDisplay(
    const char *outputName,
    const char *manufacturer,
    uint32_t *productID,
    char *serial,
    uint32_t serialCapacity
) {
    if (outputName == NULL || manufacturer == NULL || productID == NULL || serial == NULL || serialCapacity == 0) {
        return MVDDCStatusMalformedResponse;
    }
    io_iterator_t iterator = IO_OBJECT_NULL;
    kern_return_t iteratorStatus = IORegistryCreateIterator(
        kIOMainPortDefault,
        kIOServicePlane,
        kIORegistryIterateRecursively,
        &iterator
    );
    if (iteratorStatus != KERN_SUCCESS) {
        return MVDDCStatusReadFailure;
    }

    uint32_t matchCount = 0;
    bool awaitingProxy = false;
    bool hasAssociatedProxy = false;
    uint32_t candidateProductID = 0;
    char candidateSerial[128] = {0};
    io_registry_entry_t entry = IO_OBJECT_NULL;
    while ((entry = IOIteratorNext(iterator)) != IO_OBJECT_NULL) {
        if (IOObjectConformsTo(entry, "AppleCLCD2") || IOObjectConformsTo(entry, "IOMobileFramebufferShim")) {
            awaitingProxy = MVFramebufferMatchesAudioDisplay(
                entry,
                outputName,
                manufacturer,
                &candidateProductID,
                candidateSerial,
                sizeof(candidateSerial)
            );
            if (awaitingProxy) {
                matchCount += 1;
                if (matchCount == 1) {
                    *productID = candidateProductID;
                    strncpy(serial, candidateSerial, serialCapacity - 1);
                    serial[serialCapacity - 1] = '\0';
                }
            }
        } else if (awaitingProxy && MVIsExternalProxy(entry)) {
            hasAssociatedProxy = true;
            awaitingProxy = false;
        }
        IOObjectRelease(entry);
    }
    IOObjectRelease(iterator);
    if (matchCount != 1 || !hasAssociatedProxy) {
        return MVDDCStatusTargetUnavailable;
    }
    return MVDDCStatusSuccess;
}

static MVDDCStatus MVWriteVCP(
    MVIOAVFunctions functions,
    IOAVServiceRef service,
    uint8_t code,
    uint16_t value
) {
    uint8_t request[] = {
        0x84,
        0x03,
        code,
        (uint8_t)(value >> 8),
        (uint8_t)(value & 0xFF),
        0x00
    };
    request[5] = MVChecksum(request, 5, 0x6E ^ 0x51);
    bool wrote = false;
    for (uint32_t attempt = 0; attempt < 2; attempt += 1) {
        usleep(50000);
        IOReturn status = functions.writeI2C(service, 0x37, 0x51, request, sizeof(request));
        if (status == kIOReturnSuccess) {
            wrote = true;
        }
    }
    return wrote ? MVDDCStatusSuccess : MVDDCStatusWriteFailure;
}

static MVDDCWriteResult MVWriteTargetValue(
    const char *manufacturer,
    uint32_t productID,
    const char *serial,
    uint8_t code,
    uint16_t value
) {
    MVDDCWriteResult result = {MVDDCStatusTargetUnavailable, 0, 0};
    if (manufacturer == NULL) {
        result.status = MVDDCStatusMalformedResponse;
        return result;
    }
    MVIOAVFunctions functions = {0};
    if (!MVLoadIOAVFunctions(&functions)) {
        result.status = MVDDCStatusReadFailure;
        return result;
    }

    IOAVServiceRef service = NULL;
    result.status = MVCreateTargetService(
        functions,
        manufacturer,
        productID,
        serial,
        &service
    );
    if (result.status == MVDDCStatusSuccess) {
        result.status = MVWriteVCP(functions, service, code, value);
    }
    if (result.status == MVDDCStatusSuccess) {
        usleep(250000);
        result.status = MVReadVCP(
            functions,
            service,
            code,
            &result.current,
            &result.maximum
        );
    }
    if (service != NULL) {
        CFRelease(service);
    }
    dlclose(functions.handle);
    return result;
}

MVDDCReadResult MVDDCReadTargetState(
    const char *manufacturer,
    uint32_t productID,
    const char *serial
) {
    MVDDCReadResult result = {
        MVDDCStatusTargetUnavailable,
        0,
        0,
        0,
        0,
        MVDDCStatusTargetUnavailable
    };
    if (manufacturer == NULL) {
        result.status = MVDDCStatusMalformedResponse;
        return result;
    }
    MVIOAVFunctions functions = {0};
    if (!MVLoadIOAVFunctions(&functions)) {
        result.status = MVDDCStatusReadFailure;
        return result;
    }

    IOAVServiceRef service = NULL;
    result.status = MVCreateTargetService(
        functions,
        manufacturer,
        productID,
        serial,
        &service
    );
    if (result.status == MVDDCStatusSuccess) {
        result.status = MVReadVCP(
            functions,
            service,
            0x62,
            &result.volumeCurrent,
            &result.volumeMaximum
        );
    }
    if (result.status == MVDDCStatusSuccess) {
        result.muteStatus = MVReadVCP(
            functions,
            service,
            0x8D,
            &result.muteCurrent,
            &result.muteMaximum
        );
    }
    if (service != NULL) {
        CFRelease(service);
    }
    dlclose(functions.handle);
    return result;
}

MVDDCWriteResult MVDDCWriteTargetVolume(
    const char *manufacturer,
    uint32_t productID,
    const char *serial,
    uint16_t volume
) {
    return MVWriteTargetValue(manufacturer, productID, serial, 0x62, volume);
}

MVDDCWriteResult MVDDCWriteTargetMute(
    const char *manufacturer,
    uint32_t productID,
    const char *serial,
    uint16_t mute
) {
    return MVWriteTargetValue(manufacturer, productID, serial, 0x8D, mute);
}
