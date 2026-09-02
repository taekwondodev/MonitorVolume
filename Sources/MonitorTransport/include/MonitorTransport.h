#ifndef PRO_ART_VOLUME_MONITOR_TRANSPORT_H
#define PRO_ART_VOLUME_MONITOR_TRANSPORT_H

#include <stdint.h>

typedef enum {
    PAVDDCStatusSuccess = 0,
    PAVDDCStatusTargetUnavailable = 1,
    PAVDDCStatusReadFailure = 2,
    PAVDDCStatusMalformedResponse = 3,
    PAVDDCStatusWriteFailure = 4
} PAVDDCStatus;

typedef struct {
    PAVDDCStatus status;
    uint16_t volumeCurrent;
    uint16_t volumeMaximum;
    uint16_t muteCurrent;
    uint16_t muteMaximum;
} PAVDDCReadResult;

typedef struct {
    PAVDDCStatus status;
    uint16_t current;
    uint16_t maximum;
} PAVDDCWriteResult;

PAVDDCReadResult PAVDDCReadTargetState(
    const char *manufacturer,
    uint32_t productID,
    const char *serial
);

PAVDDCWriteResult PAVDDCWriteTargetVolume(
    const char *manufacturer,
    uint32_t productID,
    const char *serial,
    uint16_t volume
);

PAVDDCWriteResult PAVDDCWriteTargetMute(
    const char *manufacturer,
    uint32_t productID,
    const char *serial,
    uint16_t mute
);

#endif
