# Low-Level Design Document (LLDD)

## Module: src

### Relationships & Calls

```mermaid
flowchart TD
    sym_0["CLASS: SequenceBuilderApplication"]
    sym_1["CLASS: Constants"]
    sym_2["CLASS: DateTimeDTO"]
    sym_3["CLASS: SequenceKeyDTO"]
    sym_4["CLASS: SolverResponseDTO"]
    sym_5["CLASS: SolverResponseSummaryDTO"]
    sym_6["CLASS: StudentScheduleDTO"]
    sym_7["CLASS: FlightLegDTO"]
    sym_8["CLASS: EmployeeActivityDTO"]
    sym_9["CLASS: AccessTokenDTO"]
    sym_10["CLASS: PlaceHolderEvents"]
    sym_11["CLASS: CKAScheduleDTO"]
    sym_12["CLASS: SnapshotSolutionRequestInputDTO"]
    sym_13["CLASS: LocalDateDeserializer"]
    sym_14["CLASS: MyErrorResponse"]
    sym_15["CLASS: OEActivityDTO"]
    sym_16["CLASS: FetchJobOutputDTO"]
    sym_17["CLASS: FlightDutyPeriodDTO"]
    sym_18["CLASS: LocalDateSerializer"]
    sym_19["CLASS: SequenceDTO"]
    sym_20["CLASS: FARedeyeRule"]
    sym_21["CLASS: PilotDomesticSequenceRule"]
    sym_22["CLASS: WOCL"]
    sym_23["CLASS: ThreeAMHBT"]
    sym_24["CLASS: BaseLayover"]
    sym_25["CLASS: PilotRedeyeRule"]
    sym_26["CLASS: AzureBlobRepositoryImpl"]
    sym_27["CLASS: AzureBlobRepository"]
    sym_28["CLASS: PingFederateTokenClient"]
    sym_29["CLASS: AccessTokenClient"]
    sym_30["CLASS: QLAClientImpl"]
    sym_31["CLASS: OutputDataRepositoryImpl"]
    sym_32["CLASS: PingFederateTokenClientImpl"]
    sym_33["CLASS: AccessTokenClientImpl"]
    sym_34["CLASS: LegDataRepository"]
    sym_35["CLASS: QLAClient"]
    sym_36["CLASS: InputDataRepositoryImpl"]
    sym_37["CLASS: LegDataRepositoryImpl"]
    sym_38["CLASS: InputDataRespository"]
    sym_39["CLASS: OutputDataRepository"]
    sym_40["CLASS: KafkaProducerListener"]
    sym_41["CLASS: JsonUtil"]
    sym_42["CLASS: SurfaceLegLoader"]
    sym_43["CLASS: TAPIUtil"]
    sym_44["CLASS: SnapshotValidator"]
    sym_45["CLASS: StringUtil"]
    sym_46["CLASS: FSOFileWriter"]
    sym_47["CLASS: StationTimeAdjustLoader"]
    sym_48["CLASS: FSOUtil"]
    sym_49["CLASS: CompressUtil"]
    sym_50["CLASS: SecurityConfig"]
    sym_51["CLASS: AzureBlobStorageConfiguration"]
    sym_52["CLASS: KafkaCallbackConfig"]
    sym_53["CLASS: KafkaConfig"]
    sym_54["CLASS: KafkaConsumerConfig"]
    sym_55["CLASS: KafkaProducerConfig"]
    sym_56["CLASS: ServicePrincipalAuthCallbackSB"]
    sym_57["CLASS: ShortestPathComponent"]
    sym_58["CLASS: QLAProcessor"]
    sym_59["CLASS: CKAProcessor"]
    sym_60["CLASS: StaticDataProcessor"]
    sym_61["CLASS: InputValidationProcessor"]
    sym_62["CLASS: DHProcessor"]
    sym_63["CLASS: ConstructNetwork"]
    sym_64["CLASS: SequenceProcessor"]
    sym_65["CLASS: CkaMapper"]
    sym_66["CLASS: StudentMapper"]
    sym_67["CLASS: SequenceMapper"]
    sym_68["CLASS: QLAMapper"]
    sym_69["CLASS: TeamsNotification"]
    sym_70["CLASS: HttpSolverController"]
    sym_71["CLASS: KillController"]
    sym_72["CLASS: AzureBlobController"]
    sym_73["CLASS: FlightController"]
    sym_74["CLASS: AppProperties"]
    sym_75["CLASS: TeamsNotifications"]
    sym_76["CLASS: LegalityInterpreterRepositoryImpl"]
    sym_77["CLASS: QlaResponse"]
    sym_78["CLASS: EmployeeQLAResponse"]
    sym_79["CLASS: LegalityInterpreter"]
    sym_80["CLASS: InvalidSeqMapper"]
    sym_81["CLASS: LegalityInterpreterRepository"]
    sym_82["CLASS: PilotLegalityResponse"]
    sym_83["CLASS: PersistenceException"]
    sym_84["CLASS: LegalityRuleResult"]
    sym_85["FUNCTION: value"]
    sym_86["FUNCTION: Result"]
    sym_87["FUNCTION: toString"]
    sym_88["CLASS: RuleResult"]
    sym_89["FUNCTION: value"]
    sym_90["FUNCTION: Rule"]
    sym_91["FUNCTION: toString"]
    sym_92["CLASS: EmployeeResponse"]
    sym_93["CLASS: PickupDuty"]
    sym_94["CLASS: DateTimeInfo"]
    sym_95["CLASS: FlightLeg"]
    sym_96["CLASS: FlightDutyPeriod"]
    sym_97["CLASS: CrewMemberKey"]
    sym_98["CLASS: SequenceDetail"]
    sym_99["CLASS: CrewMemberInfo"]
    sym_100["CLASS: ProjectedData"]
    sym_101["CLASS: ScheduledTime"]
    sym_102["CLASS: DutyPeriods"]
    sym_103["CLASS: FlightDutyPeriodKey"]
    sym_104["CLASS: SequenceInfoKey"]
    sym_105["CLASS: LocalDateTimeDeserializer"]
    sym_106["CLASS: LocalDateTimeSerializer"]
    sym_107["CLASS: BidStatus"]
    sym_108["CLASS: EmpCaatsData"]
    sym_109["CLASS: LocalDateDeserializer"]
    sym_110["CLASS: FlightKey"]
    sym_111["CLASS: SequenceInfo"]
    sym_112["CLASS: EmployeeRequest"]
    sym_113["CLASS: ValidationConstants"]
    sym_114["CLASS: PilotLegalityRequest"]
    sym_115["CLASS: TimeInfo"]
    sym_116["CLASS: LocalDateSerializer"]
    sym_117["CLASS: Employee"]
    sym_118["CLASS: FlightLegs"]
    sym_119["CLASS: StationLongitudeUtils"]
    sym_120["CLASS: QLACallableClient"]
    sym_121["CLASS: QLARestClient"]
    sym_122["CLASS: FlightLeg"]
    sym_123["CLASS: Solution"]
    sym_124["CLASS: UnsequencedLegAfterRun"]
    sym_125["CLASS: SurfaceLeg"]
    sym_126["CLASS: DutyInfo"]
    sym_127["CLASS: Sequence"]
    sym_128["CLASS: Node"]
    sym_129["CLASS: Label"]
    sym_130["CLASS: HotelCostLoader"]
    sym_131["CLASS: FlightInfo"]
    sym_132["CLASS: ProcessedInputData"]
    sym_133["CLASS: FlightDutyPeriod"]
    sym_134["CLASS: Destinations"]
    sym_135["CLASS: Base"]
    sym_136["CLASS: HotelCost"]
    sym_137["CLASS: Network"]
    sym_138["CLASS: CkaBlankPeriod"]
    sym_139["CLASS: UnsequencedLegPairing"]
    sym_140["CLASS: UnsequencedLeg"]
    sym_141["CLASS: Cka"]
    sym_142["CLASS: PositionBasedParams"]
    sym_143["CLASS: BaseResourcesDeserializer"]
    sym_144["CLASS: BaseCoterminalsMap"]
    sym_145["CLASS: PairingSolution"]
    sym_146["CLASS: FilteredFlightData"]
    sym_147["CLASS: LocalDateTimeDeserializer"]
    sym_148["CLASS: LocalDateTimeSerializer"]
    sym_149["CLASS: ITFlightKey"]
    sym_150["CLASS: CkaCredits"]
    sym_151["CLASS: FlightKey"]
    sym_152["CLASS: VacationCredit"]
    sym_153["CLASS: Coterminals"]
    sym_154["CLASS: StationTimeAdjust"]
    sym_155["CLASS: ParentSnapshotParams"]
    sym_156["CLASS: ValidationConstants"]
    sym_157["CLASS: Student"]
    sym_158["CLASS: SequencedPosition"]
    sym_159["CLASS: EmployeeActivity"]
    sym_160["CLASS: OutputData"]
    sym_161["CLASS: BaseExclusionKey"]
    sym_162["CLASS: Edge"]
    sym_163["CLASS: AvailableDHLeg"]
    sym_164["CLASS: SnapshotParams"]
    sym_165["CLASS: DHDCategorization"]
    sym_166["CLASS: UserInput"]
    sym_167["CLASS: FAR117FTRule"]
    sym_168["CLASS: FAR121FDPRule"]
    sym_169["CLASS: FAR117RestTimeRule"]
    sym_170["CLASS: FAR121RestTimeRule"]
    sym_171["CLASS: FAR117FDPRule"]
    sym_172["CLASS: FAR121FTRule"]
    sym_173["CLASS: ModelParams"]
    sym_174["CLASS: is"]
    sym_175["CLASS: OptModel"]
    sym_176["CLASS: ErrorConstants"]
    sym_177["CLASS: ITDataServiceImpl"]
    sym_178["CLASS: SolverService"]
    sym_179["CLASS: PairingGenerationService"]
    sym_180["CLASS: OptimizationService"]
    sym_181["CLASS: PairingGenerationServiceImpl"]
    sym_182["CLASS: to"]
    sym_183["CLASS: OptimizationServiceImpl"]
    sym_184["CLASS: ITDataService"]
    sym_185["CLASS: PairingHeaderServiceImpl"]
    sym_186["CLASS: RunStateManager"]
    sym_187["CLASS: OutputDataService"]
    sym_188["CLASS: InputDataService"]
    sym_189["CLASS: PairingHeaderService"]
    sym_190["CLASS: OutputDataServiceImpl"]
    sym_191["CLASS: InputDataServiceImpl"]
    sym_192["CLASS: SequenceBuilderSpringContext"]
    sym_193["CLASS: OAuthBearerTokenImpl"]
    sym_194["CLASS: KafkaProducerService"]
    sym_195["CLASS: KafkaConsumerService"]
    sym_196["CLASS: SolverException"]
    sym_197["CLASS: SolverExceptionHandler"]
    sym_198["CLASS: AzureBlobStorageException"]
    sym_199["CLASS: InvalidUserInputException"]
    sym_200["CLASS: KillRunException"]
    sym_201["CLASS: NotFoundException"]
```

# Low-Level Design Document (LLDD): Sequence Builder Module

## 1. Overview
This document details the internal architecture, class structures, and behavioral logic of the `SequenceBuilder` module. The system is designed to automate the generation of pilot sequences (pairings) while adhering to complex contractual rules (FAR 117, FAR 121, WOCL, etc.) and operational constraints. It integrates with external systems via REST APIs (PingFederate, QLA), manages data persistence through Azure Blob Storage, and utilizes an optimization engine (Xpress) for sequence construction.

The design emphasizes separation of concerns:
- **DTOs**: Data transfer objects for API contracts.
- **Models**: Internal domain entities representing the optimization graph.
- **Repositories**: Abstraction layers for data access (Blob, Input/Output).
- **Services**: Business logic orchestration.
- **Rules**: Encapsulated logic for regulatory compliance.

---

## 2. Core Architecture & Entry Point

### 2.1 Application Bootstrapping
**Class:** `SequenceBuilderApplication`
- **Location:** [`src/main/java/com/aa/fso/SequenceBuilderApplication.java:L12-12`](file:///Users/venkatesansubramanian/AntiGravityProjects/Sequence_Builder-6e0c87bc6e817c8c6919be50c1f325a806eb3d25/src/main/java/com/aa/fso/SequenceBuilderApplication.java#L12-12)
- **Behavior:** Serves as the Spring Boot entry point. It initializes the application context, enabling component scanning for all services, repositories, and controllers. No business logic resides here; it solely manages the lifecycle of the Spring container.

### 2.2 Configuration Management
**Class:** `AppProperties`
- **Location:** [`src/main/java/com/aa/fso/properties/AppProperties.java:L14-14`](file:///Users/venkatesansubramanian/AntiGravityProjects/Sequence_Builder-6e0c87bc6e817c8c6919be50c1f325a806eb3d25/src/main/java/com/aa/fso/properties/AppProperties.java#L14-14)
- **Behavior:** Binds external configuration properties (from `application.properties` or environment variables) to Java objects. It exposes nested configurations for Kafka, Azure Blob Storage, and Teams Notifications.
- **Key Fields:**
  - `teamsNotifications`: Configuration for Microsoft Teams alerting.
  - `azure`: Connection strings and container names.
  - `kafka`: Bootstrap servers and topic names.

**Class:** `SecurityConfig`
- **Location:** [`src/main/java/com/aa/fso/config/SecurityConfig.java:L16-16`](file:///Users/venkatesansubramanian/AntiGravityProjects/Sequence_Builder-6e0c87bc6e817c8c6919be50c1f325a806eb3d25/src/main/java/com/aa/fso/config/SecurityConfig.java#L16-16)
- **Behavior:** Configures Spring Security to handle OAuth2 Bearer token authentication. It defines the filter chain to validate tokens issued by PingFederate before allowing access to protected endpoints.

---

## 3. Data Transfer Objects (DTOs)

The module uses a strict set of DTOs to decouple internal processing from external API contracts. These classes are typically POJOs (Plain Old Java Objects) annotated with Jackson annotations for serialization.

### 3.1 Request/Response DTOs
- **`SnapshotSolutionRequestInputDTO`** ([`.../SnapshotSolutionRequestInputDTO.java:L6-6`](file:///Users/venkatesansubramanian/AntiGravityProjects/Sequence_Builder-6e0c87bc6e817c8c6919be50c1f325a806eb3d25/src/main/java/com/aa/fso/dto/SnapshotSolutionRequestInputDTO.java#L6-6)):
  - **Purpose:** Represents the payload received from the client to initiate a sequence generation run. Contains parameters like date range, base locations, and employee IDs.
- **`SolverResponseDTO`** ([`.../SolverResponseDTO.java:L7-7`](file:///Users/venkatesansubramanian/AntiGravityProjects/Sequence_Builder-6e0c87bc6e817c8c6919be50c1f325a806eb3d25/src/main/java/com/aa/fso/dto/SolverResponseDTO.java#L7-7)):
  - **Purpose:** The primary response object returned to the client upon completion. Contains the generated sequences, status, and summary metrics.
- **`SolverResponseSummaryDTO`** ([`.../SolverResponseSummaryDTO.java:L10-10`](file:///Users/venkatesansubramanian/AntiGravityProjects/Sequence_Builder-6e0c87bc6e817c8c6919be50c1f325a806eb3d25/src/main/java/com/aa/fso/dto/SolverResponseSummaryDTO.java#L10-10)):
  - **Purpose:** A lightweight summary containing counts of valid/invalid sequences, total cost, and execution time.

### 3.2 Domain-Specific DTOs
- **`SequenceDTO`** ([`.../SequenceDTO.java:L11-11`](file:///Users/venkatesansubramanian/AntiGravityProjects/Sequence_Builder-6e0c87bc6e817c8c6919be50c1f325a806eb3d25/src/main/java/com/aa/fso/dto/SequenceDTO.java#L11-11)):
  - **Purpose:** Represents a single generated pairing. Includes a list of `FlightLegDTO` objects and associated `EmployeeActivityDTO`.
- **`FlightLegDTO`** ([`.../FlightLegDTO.java:L10-10`](file:///Users/venkatesansubramanian/AntiGravityProjects/Sequence_Builder-6e0c87bc6e817c8c6919be50c1f325a806eb3d25/src/main/java/com/aa/fso/dto/FlightLegDTO.java#L10-10)):
  - **Purpose:** Describes a single flight segment (Origin, Destination, Departure Time, Arrival Time, Aircraft Type).
- **`EmployeeActivityDTO`** ([`.../EmployeeActivityDTO.java:L13-13`](file:///Users/venkatesansubramanian/AntiGravityProjects/Sequence_Builder-6e0c87bc6e817c8c6919be50c1f325a806eb3d25/src/main/java/com/aa/fso/dto/EmployeeActivityDTO.java#L13-13)):
  - **Purpose:** Aggregates activities for an employee within a sequence (e.g., Duty Periods, Rest Periods).
- **`DateTimeDTO`** ([`.../DateTimeDTO.java:L13-13`](file:///Users/venkatesansubramanian/AntiGravityProjects/Sequence_Builder-6e0c87bc6e817c8c6919be50c1f325a806eb3d25/src/main/java/com/aa/fso/dto/DateTimeDTO.java#L13-13)):
  - **Purpose:** Standardizes date/time representation across the module, often wrapping `java.time.LocalDateTime`.

### 3.3 Specialized DTOs
- **`AccessTokenDTO`** ([`.../AccessTokenDTO.java:L8-8`](file:///Users/venkatesansubramanian/AntiGravityProjects/Sequence_Builder-6e0c87bc6e817c8c6919be50c1f325a806eb3d25/src/main/java/com/aa/fso/dto/AccessTokenDTO.java#L8-8)):
  - **Purpose:** Holds the OAuth2 bearer token required for authenticating with downstream services (e.g., QLA, Azure).
- **`PlaceHolderEvents`** ([`.../PlaceHolderEvents.java:L6-6`](file:///Users/venkatesansubramanian/AntiGravityProjects/Sequence_Builder-6e0c87bc6e817c8c6919be50c1f325a806eb3d25/src/main/java/com/aa/fso/dto/PlaceHolderEvents.java#L6-6)):
  - **Purpose:** Used to represent non-flight events (e.g., training, leave) in the schedule.
- **`CKAScheduleDTO`** / **`StudentScheduleDTO`** ([`.../CKAScheduleDTO.java:L9-9`](file:///Users/venkatesansubramanian/AntiGravityProjects/Sequence_Builder-6e0c87bc6e817c8c6919be50c1f325a806eb3d25/src/main/java/com/aa/fso/dto/CKAScheduleDTO.java#L9-9), [`.../StudentScheduleDTO.java:L7-7`](file:///Users/venkatesansubramanian/AntiGravityProjects/Sequence_Builder-6e0c87bc6e817c8c6919be50c1f325a806eb3d25/src/main/java/com/aa/fso/dto/StudentScheduleDTO.java#L7-7)):
  - **Purpose:** Specific DTOs for Crew Training (CKA) and Student Pilot scheduling scenarios.

### 3.4 Custom Serialization
To ensure consistent date handling, the module implements custom Jackson serializers/deserializers:
- **`LocalDateSerializer`** / **`LocalDateDeserializer`** ([`.../LocalDateSerializer.java:L13-13`](file:///Users/venkatesansubramanian/AntiGravityProjects/Sequence_Builder-6e0c87bc6e817c8c6919be50c1f325a806eb3d25/src/main/java/com/aa/fso/dto/LocalDateSerializer.java#L13-13), [`.../LocalDateDeserializer.java:L11-11`](file:///Users/venkatesansubramanian/AntiGravityProjects/Sequence_Builder-6e0c87bc6e817c8c6919be50c1f325a806eb3d25/src/main/java/com/aa/fso/dto/LocalDateDeserializer.java#L11-11)):
  - **Behavior:** Converts `java.time.LocalDate` to/from ISO-8601 string format (`yyyy-MM-dd`).
- **`LocalDateTimeSerializer`** / **`LocalDateTimeDeserializer`** ([`.../LocalDateTimeSerializer.java:L12-12`](file:///Users/venkatesansubramanian/AntiGravityProjects/Sequence_Builder-6e0c87bc6e817c8c6919be50c1f325a806eb3d25/src/main/java/com/aa/fso/dto/LocalDateTimeSerializer.java#L12-12), [`.../LocalDateTimeDeserializer.java:L12-12`](file:///Users/venkatesansubramanian/AntiGravityProjects/Sequence_Builder-6e0c87bc6e817c8c6919be50c1f325a806eb3d25/src/main/java/com/aa/fso/dto/LocalDateTimeDeserializer.java#L12-12)):
  - **Behavior:** Converts `java.time.LocalDateTime` to/from ISO-8601 string format (`yyyy-MM-dd'T'HH:mm:ss`).

---

## 4. Repository Layer (Data Access)

The repository layer abstracts data storage mechanisms, primarily focusing on Azure Blob Storage for large datasets and in-memory caching for performance.

### 4.1 Azure Blob Storage
**Interface:** `AzureBlobRepository` ([`.../AzureBlobRepository.java:L15-15`](file:///Users/venkatesansubramanian/AntiGravityProjects/Sequence_Builder-6e0c87bc6e817c8c6919be50c1f325a806eb3d25/src/main/java/com/aa/fso/repository/AzureBlobRepository.java#L15-15))
**Implementation:** `AzureBlobRepositoryImpl` ([`.../AzureBlobRepositoryImpl.java:L25-25`](file:///Users/venkatesansubramanian/AntiGravityProjects/Sequence_Builder-6e0c87bc6e817c8c6919be50c1f325a806eb3d25/src/main/java/com/aa/fso/repository/AzureBlobRepositoryImpl.java#L25-25))
- **Behavior:**
  - Provides methods to upload JSON payloads to specific blob paths (e.g., `/input/{snapshotId}/data.json`).
  - Handles downloading and parsing input data.
  - Implements retry logic for transient network failures.
  - Uses `AzureBlobStorageConfiguration` for connection management.

### 4.2 Input/Output Data Repositories
**Interfaces:** `InputDataRespository` ([`.../InputDataRespository.java:L13-13`](file:///Users/venkatesansubramanian/AntiGravityProjects/Sequence_Builder-6e0c87bc6e817c8c6919be50c1f325a806eb3d25/src/main/java/com/aa/fso/repository/InputDataRespository.java#L13-13)), `OutputDataRepository` ([`.../OutputDataRepository.java:L6-6`](file:///Users/venkatesansubramanian/AntiGravityProjects/Sequence_Builder-6e0c87bc6e817c8c6919be50c1f325a806eb3d25/src/main/java/com/aa/fso/repository/OutputDataRepository.java#L6-6))
**Implementations:** `InputDataRepositoryImpl` ([`.../InputDataRepositoryImpl.java:L55-55`](file:///Users/venkatesansubramanian/AntiGravityProjects/Sequence_Builder-6e0c87bc6e817c8c6919be50c1f325a806eb3d25/src/main/java/com/aa/fso/repository/InputDataRepositoryImpl.java#L55-55)), `OutputDataRepositoryImpl` ([`.../OutputDataRepositoryImpl.java:L16-16`](file:///Users/venkatesansubramanian/AntiGravityProjects/Sequence_Builder-6e0c87bc6e817c8c6919be50c1f325a806eb3d25/src/main/java/com/aa/fso/repository/OutputDataRepositoryImpl.java#L16-16))
- **Behavior:**
  - **Input:** Reads raw JSON from Blob Storage, deserializes into `ProcessedInputData`, and validates structure.
  - **Output:** Serializes the final solution (`SolverResponseDTO`) and writes it back to Blob Storage.
  - **LegData:** `LegDataRepository` / `LegDataRepositoryImpl` ([`.../LegDataRepository.java:L12-12`](file:///Users/venkatesansubramanian/AntiGravityProjects/Sequence_Builder-6e0c87bc6e817c8c6919be50c1f325a806eb3d25/src/main/java/com/aa/fso/repository/LegDataRepository.java#L12-12)) handles specific flight leg data caching.

### 4.3 External Client Repositories
These classes act as HTTP clients for external services.
- **`PingFederateTokenClient`** / **`PingFederateTokenClientImpl`** ([`.../PingFederateTokenClient.java:L3-3`](file:///Users/venkatesansubramanian/AntiGravityProjects/Sequence_Builder-6e0c87bc6e817c8c6919be50c1f325a806eb3d25/src/main/java/com/aa/fso/repository/PingFederateTokenClient.java#L3-3), [`.../PingFederateTokenClientImpl.java:L21-21`](file:///Users/venkatesansubramanian/AntiGravityProjects/Sequence_Builder-6e0c87bc6e817c8c6919be50c1f325a806eb3d25/src/main/java/com/aa/fso/repository/PingFederateTokenClientImpl.java#L21-21)):
  - **Behavior:** Authenticates with PingFederate using a Service Principal (Client ID/Secret) to obtain an access token. Implements token refresh logic.
- **`AccessTokenClient`** / **`AccessTokenClientImpl`** ([`.../AccessTokenClient.java:L5-5`](file:///Users/venkatesansubramanian/AntiGravityProjects/Sequence_Builder-6e0c87bc6e817c8c6919be50c1f325a806eb3

---