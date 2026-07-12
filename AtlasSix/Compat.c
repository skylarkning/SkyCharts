#include <stddef.h>

/* The legacy SDK stub used by this toolchain omits memset from libSystem. */
void *memset(void *destination, int value, size_t length) {
    unsigned char *bytes = (unsigned char *)destination;
    while (length--) *bytes++ = (unsigned char)value;
    return destination;
}
