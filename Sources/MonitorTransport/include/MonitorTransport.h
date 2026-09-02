#ifndef PRO_ART_VOLUME_MONITOR_TRANSPORT_H
#define PRO_ART_VOLUME_MONITOR_TRANSPORT_H

#include <stdint.h>

typedef enum {
    PAVDDCStatusSuccess = 0,
    PAVDDCStatusTargetUnavailable = 1,
    PAVDDCStatusReadFailure = 2,
    PAVDDCStatusMalformedResponse = 3
} PAVDDCStatus;

typedef struct {
    PAVDDCStatus status;
    uint16_t volumeCurrent;
    uint16_t volumeMaximum;
    uint16_t muteCurrent;
} PAVDDCReadResult;

PAVDDCReadResult PAVDDCReadTargetState(
    const char *manufacturer,
    uint32_t productID,
    const char *serial
);

#endif
