# Licensed QNX SDP 8.0 is required. Host-only tests do not compile this source.
QCC ?= qcc
QNX_VARIANT ?= gcc_ntox86_64
CFLAGS ?= -std=c11 -Wall -Wextra -Werror -O2
TARGET = faultlab_probe

.PHONY: all clean
all: $(TARGET) faultlab_inventory

$(TARGET): faultlab_probe.c
	$(QCC) -V$(QNX_VARIANT) $(CFLAGS) -o $@ $<

faultlab_inventory: inventory_demo.c
	$(QCC) -V$(QNX_VARIANT) $(CFLAGS) -o $@ $<

clean:
	rm -f $(TARGET) faultlab_inventory
