#include "contiki.h"
#include "lib/random.h"
#include "lib/aes-128.h" 
#include <stdio.h>
#include <string.h>

/* * This prevents the system from printing extra network logs 
 * that interfere with your Python data owner.
 */
#define LOG_CONF_LEVEL_IPV6 LOG_LEVEL_NONE

PROCESS(iot_node_process, "IoT Node AES");
AUTOSTART_PROCESSES(&iot_node_process);

/* The Shared Key (Must match AES_KEY_IOT in your Python script) */
static const uint8_t aes_key[16] = { 
  0x01, 0x02, 0x03, 0x04, 0x05, 0x06, 0x07, 0x08, 
  0x09, 0x0A, 0x0B, 0x0C, 0x0D, 0x0E, 0x0F, 0x10 
};

PROCESS_THREAD(iot_node_process, ev, data)
{
  static struct etimer timer;
  static uint8_t buffer[16]; 

  PROCESS_BEGIN();

  /* Initialize the AES engine with our key */
  AES_128.set_key(aes_key);

  while(1) {
    /* Send data every 10 seconds */
    etimer_set(&timer, CLOCK_SECOND * 10);
    PROCESS_WAIT_EVENT_UNTIL(etimer_expired(&timer));

    /* 1. CREATE DATA (Plaintext) */
    memset(buffer, 0, 16);
    snprintf((char *)buffer, 16, "Temp:%d", (random_rand() % 15) + 20);
    
    /* 2. ENCRYPT DATA */
    /* The AES_128.encrypt function encrypts the buffer in-place */
    AES_128.encrypt(buffer);

    /* 3. SEND ENCRYPTED DATA (Hex output only) */
    /* This loop converts the binary ciphertext into a Hex string 
       so the Python socket can read it as a line of text. */
    for(int i = 0; i < 16; i++) {
      printf("%02x", buffer[i]);
    }
    printf("\n"); /* Newline tells Python readline() that the packet is finished */
  }

  PROCESS_END();
}