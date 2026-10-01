### DB_CONNECTION_POOL_EXHAUSTION

| metric | baseline mean | baseline std | baseline min-max | incident mean | incident std | incident min-max |
|---|---|---|---|---|---|---|
| cpu_usage | 30.1 | 10.2 | 11.6-50.7 | 38.4 | 13.0 | 16.2-60.2 |
| memory_usage | 44.8 | 8.4 | 28.1-59.0 | 44.0 | 8.0 | 30.2-61.4 |
| request_rate | 114.9 | 39.4 | 35.3-182.6 | 155.7 | 77.7 | 38.8-350.4 |
| latency_ms | 107.4 | 58.2 | 16.4-212.0 | 4,951.8 | 5,346.4 | 72.1-27,018.1 |
| error_rate | 0.4 | 0.2 | 0.0-1.0 | 15.1 | 12.2 | 0.2-48.3 |
| db_connection_utilization | 27.1 | 7.6 | 10.4-43.1 | 97.1 | 2.2 | 77.1-100.0 |
| downstream_latency_ms | 123.1 | 42.7 | 62.0-218.6 | 134.5 | 41.4 | 68.6-234.6 |

### MEMORY_LEAK

| metric | baseline mean | baseline std | baseline min-max | incident mean | incident std | incident min-max |
|---|---|---|---|---|---|---|
| cpu_usage | 30.9 | 9.3 | 17.7-49.0 | 39.7 | 13.2 | 14.4-62.1 |
| memory_usage | 45.7 | 7.7 | 27.4-57.8 | 84.5 | 19.0 | 27.7-99.6 |
| request_rate | 117.7 | 61.0 | 23.6-226.4 | 120.0 | 53.3 | 14.8-217.8 |
| latency_ms | 110.9 | 62.3 | 25.5-366.5 | 313.8 | 222.8 | 21.6-2,151.7 |
| error_rate | 0.2 | 0.2 | 0.0-0.9 | 6.4 | 7.5 | 0.0-28.3 |
| db_connection_utilization | 29.3 | 6.9 | 13.6-41.8 | 28.1 | 6.8 | 14.4-43.5 |
| downstream_latency_ms | 119.0 | 38.0 | 60.0-210.9 | 111.0 | 38.5 | 54.0-224.2 |

### DOWNSTREAM_SERVICE_TIMEOUT

| metric | baseline mean | baseline std | baseline min-max | incident mean | incident std | incident min-max |
|---|---|---|---|---|---|---|
| cpu_usage | 25.4 | 8.8 | 7.8-42.5 | 24.3 | 10.0 | 9.6-41.6 |
| memory_usage | 44.7 | 7.7 | 30.4-56.9 | 45.5 | 6.9 | 32.2-58.2 |
| request_rate | 132.0 | 98.0 | 31.7-410.5 | 149.3 | 108.7 | 39.7-450.8 |
| latency_ms | 134.2 | 70.0 | 17.6-381.8 | 1,812.3 | 2,179.9 | 362.0-8,274.6 |
| error_rate | 0.3 | 0.2 | 0.0-1.1 | 10.1 | 9.7 | 0.0-40.7 |
| db_connection_utilization | 27.1 | 4.6 | 15.8-35.7 | 36.8 | 19.2 | 13.3-79.2 |
| downstream_latency_ms | 123.5 | 45.3 | 63.3-277.3 | 2,203.2 | 2,079.9 | 695.7-8,277.2 |

### NORMAL

| metric | baseline mean | baseline std | baseline min-max | incident mean | incident std | incident min-max |
|---|---|---|---|---|---|---|
| cpu_usage | 23.4 | 7.8 | 13.5-43.6 | 24.6 | 7.9 | 14.7-39.8 |
| memory_usage | 41.1 | 11.9 | 22.9-60.1 | 43.1 | 9.5 | 24.3-65.7 |
| request_rate | 115.7 | 76.8 | 22.4-229.1 | 102.4 | 66.1 | 22.0-233.0 |
| latency_ms | 122.3 | 92.7 | 20.0-299.8 | 104.8 | 101.6 | 20.2-461.5 |
| error_rate | 0.3 | 0.2 | 0.0-0.9 | 0.3 | 0.2 | 0.0-0.9 |
| db_connection_utilization | 26.4 | 4.7 | 14.3-33.9 | 27.0 | 6.9 | 16.4-47.5 |
| downstream_latency_ms | 145.7 | 52.4 | 83.2-301.8 | 145.1 | 62.5 | 81.2-383.2 |

### Signals: DB_CONNECTION_POOL_EXHAUSTION

| incident_id | variant | focus | severity | base_db_connection_utilization | peak_db_connection_utilization | latency_ratio | error_delta | cpu_ratio | timeout_per_min_baseline | timeout_per_min_incident |
|---|---|---|---|---|---|---|---|---|---|---|
| INC-003 | connection_leak | recommendation-service | CRITICAL | 21.78 | 98.21 | 325.52 | 44.43 | 1.28 | 0.03 | 5.89 |
| INC-005 | slow_query | orders-api | CRITICAL | 22.19 | 98.84 | 49.20 | 37.79 | 1.17 | 0.00 | 5.65 |
| INC-006 | slow_query | inventory-service | HIGH | 36.21 | 97.89 | 49.57 | 13.69 | 1.35 | 0.00 | 5.35 |
| INC-007 | pool_misconfig | orders-api | MEDIUM | 24.14 | 100.00 | 29.57 | 2.63 | 1.51 | 0.00 | 0.32 |
| INC-011 | connection_leak | payment-api | HIGH | 37.91 | 97.66 | 68.12 | 24.08 | 1.50 | 0.00 | 7.33 |
| INC-012 | traffic_surge | inventory-service | HIGH | 14.46 | 97.09 | 44.99 | 10.91 | 2.13 | 0.00 | 4.12 |
| INC-015 | pool_misconfig | recommendation-service | CRITICAL | 23.05 | 97.73 | 43.72 | 48.19 | 1.21 | 0.00 | 7.21 |
| INC-024 | connection_leak | payment-api | HIGH | 37.29 | 99.26 | 32.33 | 9.51 | 1.44 | 0.00 | 1.86 |
| INC-026 | pool_misconfig | orders-api | CRITICAL | 24.90 | 97.52 | 33.53 | 25.53 | 1.40 | 0.00 | 2.99 |
| INC-027 | traffic_surge | recommendation-service | MEDIUM | 28.35 | 97.41 | 57.20 | 4.23 | 1.48 | 0.00 | 1.20 |

### Signals: MEMORY_LEAK

| incident_id | variant | focus | severity | base_memory_usage | mem_rise | leak_minutes_to_peak | leak_linear_r2 | leak_max_step_share | spearman_mem_latency | latency_ratio | error_delta | cpu_ratio | oom_events |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| INC-004 | session_retention | inventory-service | HIGH | 39.46 | 59.33 | 83.00 | 0.98 | 0.03 | 0.84 | 8.14 | 13.17 | 1.94 | 0.00 |
| INC-008 | library_regression | orders-api | MEDIUM | 49.34 | 47.56 | 93.00 | 1.00 | 0.04 | 0.90 | 6.21 | 5.27 | 1.55 | 0.00 |
| INC-010 | unbounded_cache | recommendation-service | CRITICAL | 53.15 | 45.29 | 70.00 | 0.99 | 0.04 | 0.92 | 6.99 | 28.14 | 1.41 | 0.00 |
| INC-013 | listener_leak | payment-api | MEDIUM | 56.94 | 41.15 | 52.00 | 0.97 | 0.05 | 0.74 | 11.90 | 4.77 | 2.08 | 1.00 |
| INC-017 | listener_leak | recommendation-service | CRITICAL | 43.83 | 53.54 | 84.00 | 0.99 | 0.04 | 0.73 | 6.48 | 27.62 | 1.55 | 0.00 |
| INC-018 | library_regression | payment-api | LOW | 51.80 | 35.25 | 99.00 | 1.00 | 0.04 | 0.77 | 2.97 | 0.21 | 1.49 | 0.00 |
| INC-020 | listener_leak | recommendation-service | HIGH | 48.24 | 49.32 | 89.00 | 0.99 | 0.03 | 0.83 | 6.38 | 12.29 | 1.18 | 0.00 |
| INC-023 | library_regression | inventory-service | CRITICAL | 28.64 | 69.87 | 139.00 | 1.00 | 0.02 | 0.80 | 7.45 | 20.57 | 1.59 | 1.00 |
| INC-028 | session_retention | orders-api | MEDIUM | 40.81 | 58.79 | 64.00 | 0.98 | 0.03 | 0.49 | 7.16 | 1.39 | 1.60 | 1.00 |
| INC-034 | unbounded_cache | orders-api | CRITICAL | 39.11 | 60.39 | 62.00 | 1.00 | 0.03 | 0.92 | 3.37 | 16.52 | 1.58 | 0.00 |

### Signals: DOWNSTREAM_SERVICE_TIMEOUT

| incident_id | variant | service | root | severity | reported_ds_ratio | reported_latency_ratio | reported_error_delta | timeout_per_min_baseline | timeout_per_min_incident | cpu_ratio | mem_delta |
|---|---|---|---|---|---|---|---|---|---|---|---|
| INC-001 | network_latency | orders-api | inventory-service | MEDIUM | 19.74 | 11.82 | 4.29 | 0.00 | 0.47 | 1.16 | 2.56 |
| INC-002 | provider_degraded | payment-api | acquirer-gateway | MEDIUM | 31.38 | 23.99 | 3.10 | 0.00 | 0.56 | 0.98 | 4.48 |
| INC-009 | dependency_overloaded | api-gateway | recommendation-service | MEDIUM | 20.38 | 5.31 | 4.64 | 0.00 | 0.94 | 0.99 | 3.22 |
| INC-016 | dependency_overloaded | api-gateway | recommendation-service | MEDIUM | 8.16 | 2.20 | 5.17 | 0.00 | 0.75 | 1.09 | 3.48 |
| INC-022 | dependency_slow | orders-api | payment-api | HIGH | 32.71 | 17.82 | 13.51 | 0.00 | 1.64 | 1.02 | 1.70 |
| INC-025 | provider_degraded | inventory-service | warehouse-api | HIGH | 8.88 | 45.26 | 17.19 | 0.00 | 1.80 | 1.29 | 2.58 |
| INC-030 | provider_degraded | payment-api | acquirer-gateway | CRITICAL | 37.15 | 38.11 | 40.47 | 0.00 | 11.85 | 1.05 | 1.32 |
| INC-031 | network_latency | orders-api | inventory-service | CRITICAL | 8.18 | 9.17 | 17.23 | 0.00 | 2.18 | 1.08 | 2.71 |
| INC-032 | provider_degraded | inventory-service | warehouse-api | MEDIUM | 27.88 | 68.86 | 6.66 | 0.00 | 2.38 | 1.23 | 3.39 |
| INC-035 | dependency_slow | orders-api | inventory-service | HIGH | 22.85 | 12.73 | 18.88 | 0.00 | 1.81 | 1.11 | 1.24 |

### NORMAL cases

| incident_id | blip | service | max_error_rate_any | longest_run_error_gt2pct_min | max_db_util_any | focus_latency_cv | focus_latency_peak_ratio | focus_memory_range | warn_logs | error_logs | warn_per_min |
|---|---|---|---|---|---|---|---|---|---|---|---|
| INC-014 | No underlying fault: benign traffic spike on inventory-service. | inventory-service | 0.98 | 0 | 47.52 | 0.08 | 1.20 | 2.12 | 102 | 60 | 0.73 |
| INC-019 | No underlying fault: benign gc pause burst on payment-api. | payment-api | 1.25 | 0 | 43.91 | 0.18 | 1.74 | 7.24 | 104 | 90 | 0.67 |
| INC-021 | No underlying fault: benign latency blip on api-gateway. | api-gateway | 1.25 | 0 | 45.06 | 0.21 | 2.39 | 2.32 | 82 | 59 | 0.61 |
| INC-029 | No underlying fault: benign dependency blip on inventory-service. | inventory-service | 0.85 | 0 | 49.63 | 0.71 | 6.06 | 2.70 | 107 | 43 | 0.66 |
| INC-033 | No underlying fault: benign slow query burst on database. | orders-api | 1.09 | 0 | 48.23 | 0.15 | 1.38 | 2.66 | 104 | 57 | 0.59 |

### Keyword presence (share of cases with >=1 WARN/ERROR match)

| keyword | DB pool | Memory leak | Downstream timeout | Normal |
|---|---|---|---|---|
| timeout / timed out / deadline | 1.00 | 0.70 | 1.00 | 0.40 |
| 'Database connection timeout' | 0.80 | 0.20 | 0.30 | 0.40 |
| pool | 1.00 | 1.00 | 1.00 | 0.80 |
| heap / GC | 1.00 | 1.00 | 1.00 | 1.00 |
| OOM / out of memory | 0.00 | 0.50 | 0.00 | 0.00 |
| HTTP 503 / 502 / 504 | 1.00 | 0.90 | 1.00 | 0.20 |
| circuit breaker / ejecting | 0.30 | 0.00 | 0.30 | 0.00 |
| retry | 0.90 | 0.90 | 1.00 | 1.00 |
