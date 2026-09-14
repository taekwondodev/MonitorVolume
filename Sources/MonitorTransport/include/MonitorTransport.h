#ifndef MONITOR_VOLUME_MONITOR_TRANSPORT_H
#define MONITOR_VOLUME_MONITOR_TRANSPORT_H

#include <stdint.h>

typedef enum {
    MVDDCStatusSuccess = 0,
    MVDDCStatusTargetUnavailable = 1,
    MVDDCStatusReadFailure = 2,
    MVDDCStatusMalformedResponse = 3,
    MVDDCStatusWriteFailure = 4,
    MVDDCStatusUnsupported = 5
} MVDDCStatus;

typedef struct {
    MVDDCStatus status;
    uint16_t volumeCurrent;
    uint16_t volumeMaximum;
    uint16_t muteCurrent;
    uint16_t muteMaximum;
    MVDDCStatus muteStatus;
} MVDDCReadResult;

typedef struct {
    MVDDCStatus status;
    uint16_t current;
    uint16_t maximum;
} MVDDCWriteResult;

MVDDCStatus MVDDCResolveAudioDisplay(
    const char *outputName,
    const char *manufacturer,
    uint32_t *productID,
    char *serial,
    uint32_t serialCapacity
);

MVDDCReadResult MVDDCReadTargetState(
    const char *manufacturer,
    uint32_t productID,
    const char *serial
);

MVDDCWriteResult MVDDCWriteTargetVolume(
    const char *manufacturer,
    uint32_t productID,
    const char *serial,
    uint16_t volume
);

MVDDCWriteResult MVDDCWriteTargetMute(
    const char *manufacturer,
    uint32_t productID,
    const char *serial,
    uint16_t mute
);

#endif
