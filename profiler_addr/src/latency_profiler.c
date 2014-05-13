/* 
 * perf address sampling self profiling demo.
 * Requires a 3.10+ kernel with PERF_SAMPLE_ADDR support and a supported Intel CPU.
 *
 * Copyright (c) 2013 Intel Corporation
 * Author: Andi Kleen
 *
 * Redistribution and use in source and binary forms, with or without
 * modification, are permitted provided that: (1) source code distributions
 * retain the above copyright notice and this paragraph in its entirety, (2)
 * distributions including binary code include the above copyright notice and
 * this paragraph in its entirety in the documentation or other materials
 * provided with the distribution
 *
 * THIS SOFTWARE IS PROVIDED ``AS IS'' AND WITHOUT ANY EXPRESS OR IMPLIED
 * WARRANTIES, INCLUDING, WITHOUT LIMITATION, THE IMPLIED WARRANTIES OF
 * MERCHANTABILITY AND FITNESS FOR A PARTICULAR PURPOSE.
 */

#include <linux/perf_event.h>
#include <stdio.h>
#include <stdlib.h>
#include <stdint.h>
#include <string.h>
#include <unistd.h>
#include <cpuid.h>
#include <stdbool.h>
#include <assert.h>
#include <dlfcn.h>
#include <time.h>
#include <sys/types.h>
#include <sys/wait.h>
#include <signal.h>
#include <errno.h>

#include "sampler.h"
#include "perf.h"
#include "cpu.h"
#include "util.h"

void print_usage() {
  printf("usage\n");
}

int execute_program(int argc, char **argv, pid_t pid, int seconds, char* output_file) {

  /* Set up perf for loads */
  struct perf_event_attr attr;
  memset(&attr, 0, sizeof(struct perf_event_attr));
  attr.type = PERF_TYPE_RAW;
  attr.size = PERF_ATTR_SIZE_VER0;
  attr.sample_type = PERF_SAMPLE_IP | PERF_SAMPLE_TID | PERF_SAMPLE_TIME | PERF_SAMPLE_ADDR | PERF_SAMPLE_ID| PERF_SAMPLE_CPU | PERF_SAMPLE_WEIGHT | PERF_SAMPLE_DATA_SRC;
  attr.sample_period = 10000;   /* Period */
  attr.exclude_kernel = 0;
  attr.precise_ip = 1;    /* Enable PEBS */
  attr.config1 = 3;     /* Load Latency threshold */
  attr.config = mem_loads_event();  /* Event */
  attr.disabled = 1;
  attr.sample_id_all = 1;

  if (attr.config == (__u64)-1) {
    printf("Unknown CPU model\n");
    exit(1);
  }

  if (pid == 0) {
    pid = execute(argv, argc);
  }

  struct perf_fd loads;
  if (perf_fd_open(&loads, &attr, BUF_SIZE_SHIFT, pid) < 0)
    err("perf event init loads");
  printf("loads event %llx\n", attr.config);

  if (perf_enable(&loads) < 0)
    err("PERF_EVENT_IOC_ENABLE");
  
  if (seconds == 0) {
    printf("waiting for process %d\n", pid);
    wait_for_process(pid);
  } else {
    printf("collecting for %d seconds...\n", seconds);
    sleep(seconds);
  }

  if (perf_disable(&loads) < 0)
    err("PERF_EVENT_IOC_DISABLE");

  write_result_samples(output_file, &loads);
  perf_fd_close(&loads);

  return 0;
}

int main(int argc, char **argv)
{
  pid_t pid = 0;
  int seconds = 0;
  char* output_file = "";

  // skip program name
  argv++;
  argc--;

  while (argc > 0) {
    
    const char *cmd = argv[0];

    if (cmd[0] != '-') {
      break;
    } 
    else if (!strcmp(cmd, "--help")) {
      print_usage();
      exit(0);
      break;
    }
    else if (!strcmp(cmd, "-p")) {
      if (argc < 2) {
        print_usage();
        exit(0);
      } else {
        pid = atoi(argv[1]);
        argv++; argv++;
        argc--; argc--;
      }
    }
    else if (!strcmp(cmd, "-o")) {
      if (argc < 2) {
        print_usage();
        exit(0);
      } else {
        output_file = argv[1];
        argv++; argv++;
        argc--; argc--;
      }
    }
    else if (!strcmp(cmd, "-t")) {
      if (argc < 2) {
        print_usage();
        exit(0);
      } else {
        seconds = atoi(argv[1]);
        argv++; argv++;
        argc--; argc--;
      }
    } else {
      printf("Unknown parameter\n");
      print_usage();
      exit(0);
    }
  }

  if (pid == 0 && argc == 0) {
    printf("No command and no pid to attach\n");
    print_usage();
    exit(0);
  }
  if (pid != 0 && argc != 0) {
    printf("PID to attach and command to execute given\n");
    print_usage();
    exit(0);
  }

	return execute_program(argc, argv, pid, seconds, output_file);
}
