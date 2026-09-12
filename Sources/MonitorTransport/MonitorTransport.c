#include "MonitorTransport.h"

#include <CoreFoundation/CoreFoundation.h>
#include <IOKit/IOKitLib.h>
#include <dlfcn.h>
#include <stdbool.h>
#include <string.h>
#include <unistd.h>

typedef CFTypeRef IOAVServiceRef;
typedef IOAVServiceRef (*PAVCreateServiceFunction)(CFAllocatorRef allocator, io_service_t service);
typedef IOReturn (*PAVReadI2CFunction)(
    IOAVServiceRef service,
    uint32_t chipAddress,
    uint32_t offset,
    void *outputBuffer,
    uint32_t outputBufferSize
);
typedef IOReturn (*PAVWriteI2CFunction)(
    IOAVServiceRef service,
    uint32_t chipAddress,
    uint32_t dataAddress,
    void *inputBuffer,
    uint32_t inputBufferSize
);

typedef struct {
    void *handle;
    PAVCreateServiceFunction createService;
    PAVReadI2CFunction readI2C;
    PAVWriteI2CFunction writeI2C;
} PAVIOAVFunctions;

static bool PAVLoadIOAVFunctions(PAVIOAVFunctions *functions) {
    functions->handle = dlopen(
        "/System/Library/Frameworks/IOKit.framework/Versions/A/IOKit",
        RTLD_LAZY | RTLD_LOCAL
    );
    if (functions->handle == NULL) {
        return false;
    }
    functions->createService = (PAVCreateServiceFunction)dlsym(
        functions->handle,
        "IOAVServiceCreateWithService"
    );
    functions->readI2C = (PAVReadI2CFunction)dlsym(functions->handle, "IOAVServiceReadI2C");
    functions->writeI2C = (PAVWriteI2CFunction)dlsym(functions->handle, "IOAVServiceWriteI2C");
    if (functions->createService == NULL || functions->readI2C == NULL || functions->writeI2C == NULL) {
        dlclose(functions->handle);
        return false;
    }
    return true;
}

static bool PAVStringMatches(CFTypeRef value, const char *expected) {
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

static bool PAVCopyString(CFTypeRef value, char *output, uint32_t capacity) {
    if (value == NULL || CFGetTypeID(value) != CFStringGetTypeID() || capacity == 0) {
        return false;
    }
    return CFStringGetCString((CFStringRef)value, output, capacity, kCFStringEncodingUTF8);
}

static bool PAVOutputNameMatches(CFTypeRef productNameValue, const char *outputName) {
    char productName[128] = {0};
    if (!PAVCopyString(productNameValue, productName, sizeof(productName))) {
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

static bool PAVNumberMatches(CFTypeRef value, uint32_t expected) {
    if (value == NULL || CFGetTypeID(value) != CFNumberGetTypeID()) {
        return false;
    }
    uint32_t actual = 0;
    return CFNumberGetValue((CFNumberRef)value, kCFNumberSInt32Type, &actual) && actual == expected;
}

static bool PAVFramebufferMatches(
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
    bool matches = PAVStringMatches(CFDictionaryGetValue(product, CFSTR("ManufacturerID")), manufacturer)
        && PAVNumberMatches(CFDictionaryGetValue(product, CFSTR("ProductID")), productID)
        && (serial == NULL
            || PAVStringMatches(CFDictionaryGetValue(product, CFSTR("AlphanumericSerialNumber")), serial));
    CFRelease(attributesValue);
    return matches;
}

static bool PAVFramebufferMatchesAudioDisplay(
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
    bool matches = PAVStringMatches(CFDictionaryGetValue(product, CFSTR("ManufacturerID")), manufacturer)
        && PAVOutputNameMatches(CFDictionaryGetValue(product, CFSTR("ProductName")), outputName)
        && productIDValue != NULL
        && CFGetTypeID(productIDValue) == CFNumberGetTypeID()
        && CFNumberGetValue((CFNumberRef)productIDValue, kCFNumberSInt32Type, &resolvedProductID);
    if (matches) {
        *productID = resolvedProductID;
        serial[0] = '\0';
        CFTypeRef serialValue = CFDictionaryGetValue(product, CFSTR("AlphanumericSerialNumber"));
        if (serialValue != NULL && CFGetTypeID(serialValue) == CFStringGetTypeID()) {
            PAVCopyString(serialValue, serial, serialCapacity);
        }
    }
    CFRelease(attributesValue);
    return matches;
}

static bool PAVIsExternalProxy(io_registry_entry_t entry) {
    if (!IOObjectConformsTo(entry, "DCPAVServiceProxy")) {
        return false;
    }
    CFTypeRef location = IORegistryEntryCreateCFProperty(
        entry,
        CFSTR("Location"),
        kCFAllocatorDefault,
        0
    );
    bool external = PAVStringMatches(location, "External");
    if (location != NULL) {
        CFRelease(location);
    }
    return external;
}

static uint8_t PAVChecksum(const uint8_t *bytes, uint32_t count, uint8_t initial) {
    uint8_t checksum = initial;
    for (uint32_t index = 0; index < count; index += 1) {
        checksum ^= bytes[index];
    }
    return checksum;
}

static PAVDDCStatus PAVReadVCP(
    PAVIOAVFunctions functions,
    IOAVServiceRef service,
    uint8_t code,
    uint16_t *current,
    uint16_t *maximum
) {
    uint8_t request[] = {0x82, 0x01, code, 0x00};
    request[3] = PAVChecksum(request, 3, 0x6E);

    IOReturn writeStatus = functions.writeI2C(service, 0x37, 0x51, request, sizeof(request));
    if (writeStatus != kIOReturnSuccess) {
        return PAVDDCStatusReadFailure;
    }
    usleep(10000);
    writeStatus = functions.writeI2C(service, 0x37, 0x51, request, sizeof(request));
    if (writeStatus != kIOReturnSuccess) {
        return PAVDDCStatusReadFailure;
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
            || PAVChecksum(reply, 10, 0x50) != reply[10]) {
            receivedMalformedResponse = true;
            continue;
        }
        if (reply[3] == 0x01) {
            return PAVDDCStatusUnsupported;
        }
        if (reply[3] != 0x00) {
            receivedMalformedResponse = true;
            continue;
        }
        *maximum = (uint16_t)((reply[6] << 8) | reply[7]);
        *current = (uint16_t)((reply[8] << 8) | reply[9]);
        return PAVDDCStatusSuccess;
    }
    return receivedMalformedResponse ? PAVDDCStatusMalformedResponse : PAVDDCStatusReadFailure;
}

static PAVDDCStatus PAVCreateTargetService(
    PAVIOAVFunctions functions,
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
        return PAVDDCStatusReadFailure;
    }

    PAVDDCStatus status = PAVDDCStatusTargetUnavailable;
    bool targetFramebuffer = false;
    io_registry_entry_t entry = IO_OBJECT_NULL;
    while ((entry = IOIteratorNext(iterator)) != IO_OBJECT_NULL) {
        if (IOObjectConformsTo(entry, "AppleCLCD2") || IOObjectConformsTo(entry, "IOMobileFramebufferShim")) {
            targetFramebuffer = PAVFramebufferMatches(entry, manufacturer, productID, serial);
        } else if (targetFramebuffer && PAVIsExternalProxy(entry)) {
            *targetService = functions.createService(kCFAllocatorDefault, entry);
            status = *targetService == NULL ? PAVDDCStatusReadFailure : PAVDDCStatusSuccess;
            IOObjectRelease(entry);
            break;
        }
        IOObjectRelease(entry);
    }

    IOObjectRelease(iterator);
    return status;
}

PAVDDCStatus PAVDDCResolveAudioDisplay(
    const char *outputName,
    const char *manufacturer,
    uint32_t *productID,
    char *serial,
    uint32_t serialCapacity
) {
    if (outputName == NULL || manufacturer == NULL || productID == NULL || serial == NULL || serialCapacity == 0) {
        return PAVDDCStatusMalformedResponse;
    }
    io_iterator_t iterator = IO_OBJECT_NULL;
    kern_return_t iteratorStatus = IORegistryCreateIterator(
        kIOMainPortDefault,
        kIOServicePlane,
        kIORegistryIterateRecursively,
        &iterator
    );
    if (iteratorStatus != KERN_SUCCESS) {
        return PAVDDCStatusReadFailure;
    }

    uint32_t matchCount = 0;
    bool awaitingProxy = false;
    bool hasAssociatedProxy = false;
    uint32_t candidateProductID = 0;
    char candidateSerial[128] = {0};
    io_registry_entry_t entry = IO_OBJECT_NULL;
    while ((entry = IOIteratorNext(iterator)) != IO_OBJECT_NULL) {
        if (IOObjectConformsTo(entry, "AppleCLCD2") || IOObjectConformsTo(entry, "IOMobileFramebufferShim")) {
            awaitingProxy = PAVFramebufferMatchesAudioDisplay(
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
        } else if (awaitingProxy && PAVIsExternalProxy(entry)) {
            hasAssociatedProxy = true;
            awaitingProxy = false;
        }
        IOObjectRelease(entry);
    }
    IOObjectRelease(iterator);
    if (matchCount != 1 || !hasAssociatedProxy) {
        return PAVDDCStatusTargetUnavailable;
    }
    return PAVDDCStatusSuccess;
}

static PAVDDCStatus PAVWriteVCP(
    PAVIOAVFunctions functions,
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
    request[5] = PAVChecksum(request, 5, 0x6E ^ 0x51);
    bool wrote = false;
    for (uint32_t attempt = 0; attempt < 2; attempt += 1) {
        usleep(50000);
        IOReturn status = functions.writeI2C(service, 0x37, 0x51, request, sizeof(request));
        if (status == kIOReturnSuccess) {
            wrote = true;
        }
    }
    return wrote ? PAVDDCStatusSuccess : PAVDDCStatusWriteFailure;
}

static PAVDDCWriteResult PAVWriteTargetValue(
    const char *manufacturer,
    uint32_t productID,
    const char *serial,
    uint8_t code,
    uint16_t value
) {
    PAVDDCWriteResult result = {PAVDDCStatusTargetUnavailable, 0, 0};
    if (manufacturer == NULL) {
        result.status = PAVDDCStatusMalformedResponse;
        return result;
    }
    PAVIOAVFunctions functions = {0};
    if (!PAVLoadIOAVFunctions(&functions)) {
        result.status = PAVDDCStatusReadFailure;
        return result;
    }

    IOAVServiceRef service = NULL;
    result.status = PAVCreateTargetService(
        functions,
        manufacturer,
        productID,
        serial,
        &service
    );
    if (result.status == PAVDDCStatusSuccess) {
        result.status = PAVWriteVCP(functions, service, code, value);
    }
    if (result.status == PAVDDCStatusSuccess) {
        usleep(250000);
        result.status = PAVReadVCP(
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

PAVDDCReadResult PAVDDCReadTargetState(
    const char *manufacturer,
    uint32_t productID,
    const char *serial
) {
    PAVDDCReadResult result = {
        PAVDDCStatusTargetUnavailable,
        0,
        0,
        0,
        0,
        PAVDDCStatusTargetUnavailable
    };
    if (manufacturer == NULL) {
        result.status = PAVDDCStatusMalformedResponse;
        return result;
    }
    PAVIOAVFunctions functions = {0};
    if (!PAVLoadIOAVFunctions(&functions)) {
        result.status = PAVDDCStatusReadFailure;
        return result;
    }

    IOAVServiceRef service = NULL;
    result.status = PAVCreateTargetService(
        functions,
        manufacturer,
        productID,
        serial,
        &service
    );
    if (result.status == PAVDDCStatusSuccess) {
        result.status = PAVReadVCP(
            functions,
            service,
            0x62,
            &result.volumeCurrent,
            &result.volumeMaximum
        );
    }
    if (result.status == PAVDDCStatusSuccess) {
        result.muteStatus = PAVReadVCP(
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

PAVDDCWriteResult PAVDDCWriteTargetVolume(
    const char *manufacturer,
    uint32_t productID,
    const char *serial,
    uint16_t volume
) {
    return PAVWriteTargetValue(manufacturer, productID, serial, 0x62, volume);
}

PAVDDCWriteResult PAVDDCWriteTargetMute(
    const char *manufacturer,
    uint32_t productID,
    const char *serial,
    uint16_t mute
) {
    return PAVWriteTargetValue(manufacturer, productID, serial, 0x8D, mute);
}
