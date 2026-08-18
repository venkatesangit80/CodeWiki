# Architecture & Operations Synthesis Document

This document details the system design, network routing boundary, and scaling characteristics derived programmatically.

## 1. System Package Topology Diagram

```mermaid
flowchart TD
    pkg_0[".metadata/.plugins/org.eclipse.pde.core"]
    pkg_1["com.aa.fso"]
    pkg_2["com.aa.fso.component"]
    pkg_3["com.aa.fso.config"]
    pkg_4["com.aa.fso.contractualrules"]
    pkg_5["com.aa.fso.controller"]
    pkg_6["com.aa.fso.dto"]
    pkg_7["com.aa.fso.exception"]
    pkg_8["com.aa.fso.listener"]
    pkg_9["com.aa.fso.mapper"]
    pkg_10["com.aa.fso.model"]
    pkg_11["com.aa.fso.optmodel"]
    pkg_12["com.aa.fso.processor"]
    pkg_13["com.aa.fso.properties"]
    pkg_14["com.aa.fso.qlacheck"]
    pkg_15["com.aa.fso.repository"]
    pkg_16["com.aa.fso.rules"]
    pkg_17["com.aa.fso.security"]
    pkg_18["com.aa.fso.service"]
    pkg_19["com.aa.fso.util"]
    pkg_20["k8s/IT/eastus-dev"]
    pkg_21["k8s/IT/eastus-qa"]
    pkg_22["k8s/IT/eastus-stage"]
    pkg_23["k8s/nonprod"]
    pkg_24["k8s/prod"]
    pkg_25["root"]
    pkg_26["src/main/resources"]
    pkg_6 --> pkg_10
    pkg_4 --> pkg_10
    pkg_15 --> pkg_1
    pkg_15 --> pkg_3
    pkg_15 --> pkg_6
    pkg_15 --> pkg_7
    pkg_15 --> pkg_10
    pkg_15 --> pkg_13
    pkg_15 --> pkg_19
    pkg_19 --> pkg_10
    pkg_19 --> pkg_1
    pkg_19 --> pkg_11
    pkg_19 --> pkg_6
    pkg_3 --> pkg_10
    pkg_3 --> pkg_8
    pkg_17 --> pkg_3
    pkg_17 --> pkg_18
    pkg_12 --> pkg_6
    pkg_12 --> pkg_7
    pkg_12 --> pkg_11
    pkg_12 --> pkg_18
    pkg_12 --> pkg_19
    pkg_12 --> pkg_10
    pkg_12 --> pkg_9
    pkg_12 --> pkg_15
    pkg_9 --> pkg_6
    pkg_9 --> pkg_10
    pkg_2 --> pkg_10
    pkg_2 --> pkg_13
    pkg_5 --> pkg_3
    pkg_5 --> pkg_6
    pkg_5 --> pkg_10
    pkg_5 --> pkg_18
    pkg_5 --> pkg_15
    pkg_14 --> pkg_13
    pkg_14 --> pkg_19
    pkg_10 --> pkg_6
    pkg_10 --> pkg_11
    pkg_10 --> pkg_18
    pkg_10 --> pkg_7
    pkg_10 --> pkg_3
    pkg_16 --> pkg_10
    pkg_16 --> pkg_19
    pkg_16 --> pkg_11
    pkg_11 --> pkg_7
    pkg_11 --> pkg_18
    pkg_11 --> pkg_10
    pkg_18 --> pkg_10
    pkg_18 --> pkg_2
    pkg_18 --> pkg_3
    pkg_18 --> pkg_6
    pkg_18 --> pkg_15
    pkg_18 --> pkg_19
    pkg_18 --> pkg_7
    pkg_18 --> pkg_11
    pkg_18 --> pkg_12
    pkg_18 --> pkg_13
    pkg_18 --> pkg_1
    pkg_7 --> pkg_2
    pkg_7 --> pkg_6
```

## 2. Ingress, Execution & Egress Boundary Flow

```mermaid
flowchart LR
    subgraph Ingress ["System Ingress (Entry Points)"]
        ing_1["Method SequenceBuilderApplication.main"]
        ing_2["Method HttpSolverController.solveDebug"]
        ing_3["Method KillController.getRunStatus"]
        ing_4["Method FlightController.getOpenLegs"]
        ing_5["Method KafkaConsumerService.consumeMessage"]
    end
    subgraph Execution ["Core Processing Execution"]
        exec_ctrl["Controllers / Request Routers"]
        exec_svc["Service Orchestrators"]
        exec_solve["Core Logic / Optimization Solver"]
        exec_ctrl --> exec_svc --> exec_solve
    end
    subgraph Egress ["System Egress (Outbound Dependencies)"]
        eg_1["Database Connectivity (e.g. Repository / Queries"]
        eg_2["File System Writes / Local I/O operations"]
        eg_3["In-Process Native C++ Execution (FICO Xpress Optimizer JNI calls"]
        eg_4["Message Queue / Kafka Producer"]
        eg_5["Outbound External HTTP/API Client"]
    end
    ing_1 --> exec_ctrl
    ing_2 --> exec_ctrl
    ing_3 --> exec_ctrl
    ing_4 --> exec_ctrl
    ing_5 --> exec_ctrl
    exec_solve --> eg_1
    exec_solve --> eg_2
    exec_solve --> eg_3
    exec_solve --> eg_4
    exec_solve --> eg_5
```


