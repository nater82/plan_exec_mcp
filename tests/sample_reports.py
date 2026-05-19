"""Fictional incident reports for robustness testing.

All reports are FICTIONAL. No real personnel, units, or events.
Designed to span common command-post report categories:
1. Trainee separation (baseline — already validated in v4)
2. Vehicle accident with injury
3. Heat casualty / medical
4. Weapon malfunction / equipment
5. Negligent discharge / range incident

Each varies in length, severity, and the categories the plan should cover.
"""

TRAINEE_SEPARATION = """INCIDENT REPORT - TRAINING EXERCISE [FICTIONAL TEST DATA]

DTG: 172347MAY26
LOCATION: Training Area 7, vicinity grid 18S TJ 12345 67890
UNIT: 2nd Platoon, B Company, 1-100 IN BN
INCIDENT TYPE: Trainee separation during night land navigation

NARRATIVE:
At approximately 2230 local, Trainee SMITH, J. (E-2) was reported overdue
at checkpoint Charlie during the night land navigation exercise. Initial
search of last-known route was initiated at 2245 by squad leader SGT JONES.
Trainee was located at 2310 approximately 400m east of expected route,
disoriented and dehydrated but otherwise uninjured. Medic on scene cleared
trainee for transport. Trainee was transported to aid station for evaluation.

Weather conditions at time of incident: light rain, visibility 200m, temp 14C,
wind from NNW at 8kt. Lunar illumination 12%.

Cross-reference: see also report TR-5/2026 (related land nav incident,
same training area, dated 14MAR26).

STATUS: Trainee released to unit at 0145, training continues with modified
night nav route. Recommend review of route marking adequacy and consider
codifying a weather-trigger pause threshold for future night nav iterations.

REPORTING NCO: SFC WILSON, M.
"""

VEHICLE_ACCIDENT = """INCIDENT REPORT - TRAINING EXERCISE [FICTIONAL TEST DATA]

DTG: 180645MAY26
LOCATION: MSR Tan, grid 18S TJ 22100 71400, approximately 2km north of Range 12
UNIT: HHC, 1-100 IN BN (convoy operations training)
INCIDENT TYPE: Vehicle rollover, single vehicle, no other parties involved

NARRATIVE:
At 0612 local, M1078 LMTV (bumper number HHC-23) traveling northbound on
MSR Tan departed the roadway on a right-hand curve and rolled onto driver
side. Vehicle had been operating at estimated 35 mph in wet conditions.
Driver SGT GARCIA, T. and assistant driver SPC LEE, K. were both wearing
seatbelts and helmets. SGT GARCIA sustained suspected fractured left clavicle.
SPC LEE complaint of neck pain, ROM limited. Both evacuated by ground
ambulance to MTF at 0640. Vehicle non-mission-capable, awaiting recovery.

Cargo: training ammunition (blank only), no live rounds, no HAZMAT.
Estimated cargo damage minimal.

Weather: heavy rain past 6 hours, road surface saturated. Speed limit on
this stretch is posted at 30 mph; preliminary indication is operator was
within 5 mph of limit.

CROSS-REFERENCE: prior near-miss incident NM-2026-09 on same curve dated
22FEB26. Recommend formal review of curve geometry and posted speed.

STATUS: Range 12 operations continued; convoy training paused pending
brief reissue. 15-6 investigation initiated by BN S-3.

REPORTING NCO: 1SG MARTINEZ, R.
"""

HEAT_CASUALTY = """INCIDENT REPORT - TRAINING EXERCISE [FICTIONAL TEST DATA]

DTG: 191420MAY26
LOCATION: Land Navigation Course, Training Area 4
UNIT: 1st Platoon, A Company, 2-200 IN BN
INCIDENT TYPE: Heat casualty (heat exhaustion progressing to heat stroke)

NARRATIVE:
At 1335 local during the day land navigation lane, Trainee BROWN, A. (E-3)
collapsed near checkpoint Foxtrot. Squad members initiated immediate cooling,
removed gear, applied ice sheets. Body temperature on initial assessment by
medic at 1342 was 104.2F. Trainee was unresponsive but breathing.

Trainee was evacuated by ground at 1351 to the Battalion Aid Station and
subsequently transferred to the regional hospital at 1430 for further
evaluation. Current status: stable, admitted for observation.

Conditions at time of incident: ambient temp 96F, heat index 108F,
WBGT reading 88F (BLACK FLAG). Trainees were on hour 5 of a 7-hour lane.
Water consumption logged: trainee had consumed approximately 1.5 quarts
since start of lane (significantly below standard).

CROSS-REFERENCE: HEAT-2025-04 (similar case, similar conditions); also
reference battalion heat category SOP dated 01APR26.

STATUS: Land nav lane was suspended at 1400 pending review. WBGT had
crossed into BLACK FLAG at 1245 — preliminary indication that the lane
should have been suspended earlier. Recommend immediate review of WBGT
trigger compliance, water consumption tracking procedures, and cadre
heat-injury recognition refresher.

REPORTING NCO: SFC TAYLOR, D.
NEXT-OF-KIN NOTIFICATION: Initiated by Rear-D NCO at 1500.
"""

WEAPON_MALFUNCTION = """INCIDENT REPORT - TRAINING EXERCISE [FICTIONAL TEST DATA]

DTG: 200915MAY26
LOCATION: Range 8, firing point 12
UNIT: 3rd Platoon, C Company, 1-100 IN BN
INCIDENT TYPE: Weapon malfunction — possible barrel obstruction, M4A1

NARRATIVE:
During qualification fire at 0855, SPC RODRIGUEZ, P. experienced a stoppage
on his M4A1 (serial M4-024815) at firing point 12. Per immediate action drill,
trainee attempted to clear; second attempt revealed possible barrel
obstruction. Trainee correctly ceased fire and notified tower.

Weapon was rendered safe and removed from line. Visual inspection of barrel
revealed apparent debris approximately 15cm from chamber. Weapon has been
tagged and impounded pending armorer inspection. No injuries.

Range was placed in administrative hold at 0902 for line safety check.
All other weapons on the line were inspected; no additional issues found.
Range resumed firing at 0935.

This is the second M4A1 malfunction on Range 8 this training cycle.
Previous incident: WMR-2026-018 dated 15MAY26 (different weapon, different
trainee, similar barrel obstruction presentation).

STATUS: Trainee continued qualification with replacement weapon. Armorer
inspection of M4-024815 pending. Recommend review of weapons maintenance
procedures and consideration of additional pre-fire inspection by cadre.

REPORTING NCO: SSG ANDERSON, B.
"""

NEGLIGENT_DISCHARGE = """INCIDENT REPORT - TRAINING EXERCISE [FICTIONAL TEST DATA]

DTG: 211135MAY26
LOCATION: Range 14, ammunition clearing barrel, adjacent to firing line
UNIT: 4th Platoon, A Company, 1-100 IN BN
INCIDENT TYPE: Negligent discharge of M4A1 at clearing barrel

NARRATIVE:
At 1118 local, following completion of his qualification iteration,
PFC NGUYEN, T. discharged one round from his M4A1 into the clearing
barrel during the post-fire weapons clearance procedure.

Sequence per witness statements and tower observation:
- Trainee fired qualification, expended assigned ammunition
- Approached clearing barrel as directed
- Failed to perform full clearing sequence (did not remove magazine
  before locking bolt to rear and visually inspecting chamber)
- Inserted muzzle into clearing barrel and pulled trigger
- One 5.56mm round discharged into clearing barrel; no injuries,
  no equipment damage outside clearing barrel itself

Range was placed in immediate cease-fire at 1119. All weapons re-cleared
under direct cadre supervision. Trainee was removed from line and
re-briefed on clearing procedures by senior NCO.

CROSS-REFERENCE: this is the first ND in this training cycle. Last ND
in this battalion was DCH-2025-11 (different range, different unit,
December 2025).

STATUS: Trainee continues training per command guidance, with additional
remedial weapons safety instruction prior to next live-fire iteration.
1-100 IN BN CDR and CSM both notified at 1145. CDR has directed
unit-wide weapons safety stand-down brief prior to next training day.

Recommend formal AAR within 72 hours and review of cadre supervision
ratios at clearing barrels (current ratio 1:4, recommend reducing to 1:2
for trainee-level units).

REPORTING NCO: SFC JOHNSON, K.
"""


ALL_REPORTS = {
    "trainee_separation": TRAINEE_SEPARATION,
    "vehicle_accident": VEHICLE_ACCIDENT,
    "heat_casualty": HEAT_CASUALTY,
    "weapon_malfunction": WEAPON_MALFUNCTION,
    "negligent_discharge": NEGLIGENT_DISCHARGE,
}
