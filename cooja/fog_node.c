#include "contiki.h"
#include "net/ipv6/simple-udp.h"
#include <stdio.h>

#define UDP_PORT 1234

static struct simple_udp_connection udp_conn;

PROCESS(fog_node_process, "Fog Node");
AUTOSTART_PROCESSES(&fog_node_process);

static void receiver(struct simple_udp_connection *c,
                     const uip_ipaddr_t *sender_addr,
                     uint16_t sender_port,
                     const uip_ipaddr_t *receiver_addr,
                     uint16_t receiver_port,
                     const uint8_t *data,
                     uint16_t datalen)
{
  printf("Fog received: %.*s\n", datalen, (char *)data);
}

PROCESS_THREAD(fog_node_process, ev, data)
{
  PROCESS_BEGIN();

  simple_udp_register(&udp_conn, UDP_PORT, NULL, UDP_PORT, receiver);

  PROCESS_END();
}