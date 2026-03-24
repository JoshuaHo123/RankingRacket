# MascotGO Atlas Database - Data Export

**Export Date:** 2025  
**Source Database:** mascotgo-atlas  
**Export Location:** `./data/`  
**Total Tables:** 54  
**Total Records:** ~15.8 million rows

This directory contains a complete export of the MascotGO Atlas database in CSV format. All data has been exported from Microsoft SQL Server using Entity Framework Core and is ready for analysis in Excel, R, Python, Tableau, or other analytical tools.

---

## Table of Contents

- [Geographic Data](#geographic-data) (6 tables)
- [Administrative Data](#administrative-data) (1 table)
- [School Data](#school-data) (3 tables)
- [College Core Data](#college-core-data) (5 tables)
- [College Detailed Data](#college-detailed-data) (26 tables)
- [Peer College Data](#peer-college-data) (1 table)
- [Classification Systems](#classification-systems) (10 tables)
- [System Tables](#system-tables) (2 tables)

---

## Snowflake ID Format

Throughout this export, unique identifiers (IDs) are represented in Snowflake ID format. Snowflake IDs are 64-bit integers encoded as strings to ensure compatibility across systems. They can be used to uniquely identify records and establish relationships between tables.

Think of these as a more compact form of GUID, however, they actually have an interesting property to them in that they can 
be sorted chronologically within about a two-second accuracy. This is because the first 42 bits of a Snowflake ID represent a timestamp in milliseconds since a custom epoch (January 1, 2020). The remaining bits are used for machine identification and sequence numbers to ensure uniqueness.

Snowflakes are generated using a very specific distributed algorithm that ensures uniqueness across multiple machines without requiring a central authority. This makes them ideal for distributed systems where records may be created simultaneously on different servers.

For purposes herein, all you need to know is that they represent a unique identifier for records in the database and can be used to join tables together.

---


## Geographic Data

Basic geographic reference data for regions, countries, states, cities, and postal codes. Note that the city, state and postal codes are limited herein to the United States, but we actually have this data for most of the world.

### Regions
**Rows:** 6  
World regions based on United Nations geoscheme classifications (e.g., Africa, Americas, Asia, Europe, Oceania).

### SubRegions
**Rows:** 23  
Sub-regions within major world regions providing more granular geographic classifications (e.g., Northern Africa, South America, Eastern Asia).

### Countries
**Rows:** 250  
Comprehensive country data including ISO codes, currency information, phone codes, geographic coordinates, population, and spatial geometry for mapping.

### States
**Rows:** 66  
State and province data for countries worldwide, including U.S. states, Canadian provinces, and other administrative divisions with geographic coordinates.

### Cities
**Rows:** 45,892  
Major cities worldwide with geographic coordinates, state/country associations, and spatial geometry for location-based queries and mapping.

### PostalCodes
**Rows:** 4,141,109  
Postal code data (ZIP codes in the U.S.) with associated cities, states, and precise geographic coordinates for address validation and geocoding.

---

## Administrative Data

Many of the data sets published by the U.S. governement uses an ANSI state code instead of some other more common method. This table 
simply maps those codes to state names.

### AnsiStates
**Rows:** 57  
ANSI (American National Standards Institute) state codes and names providing standardized two-letter abbreviations for U.S. states and territories.

---

## High School Data

Data relating to high schools.

### SchoolDistricts
**Rows:** 19,637  
School district information from NCES including enrollment, staff counts (teachers, administrators, support staff), geographic location, and district type classifications.

### PublicSchools
**Rows:** 106,135  
Public K-12 school data from NCES including enrollment, grades offered, location, district affiliation, Title I status, and school characteristics (charter, magnet, virtual).

### PrivateSchools
**Rows:** ~106,000  
Private and religious school data from the Private School Survey (PSS) including enrollment, religious affiliation, school level, tuition, and demographic information.

---

## College Core Data

This is the primary set of data that will matter to most products. 

**UrbanColleges** is the starting point from the core IPEDS government data set. All other college-related tables will join to it via the `UnitId` column.

### UrbanColleges
**Rows:** 6,163  
Primary college and university directory from the Urban Institute's Education Data API containing institutional characteristics, contact information, Carnegie classifications, control type, and operational status.

### HistoricalUrbanColleges

Do not use this table. It's simply very old historical data we captured.

**Rows:** ~2,747  
Historical records of closed or merged colleges and universities (1980-2022) preserving institutional memory for longitudinal analysis.

### CollegeAliases
**Rows:** ~1,000  
Alternative names and abbreviations for colleges (e.g., "MIT" for Massachusetts Institute of Technology) with popularity scores for search optimization.

### CollegeNamePreferences

These are the `good` college names. The names reported by many schools to IPEDS are often inconsistent or have strange formatting. This table provides a curated set of preferred names for display purposes.

This table was created by using LLMs to suggest the most common name for each school. Some schools may have multiple names and are represented multiple times here.

**Rows:** ~6,000  
Curated, user-friendly display names for colleges that normalize institutional naming conventions for consistent presentation.

### CollegeSlugPreferences

The `slug` will be used for creating URL-friendly identifiers for colleges on our website. These were computed to be unique and representative of the school name where possible.

**Rows:** ~6,000  
URL-friendly identifiers (slugs) for colleges ensuring unique, readable web addresses for institutional profiles.

---

## College Detailed Data

### UrbanCollegeCharacteristics
**Rows:** 6,049  
Institutional characteristics including calendar system, degree offerings, housing options, student services, ROTC programs, library facilities, and NCAA membership.

### UrbanCollegeAdmissions
**Rows:** 8,677  
Admissions data by gender including number of applications, admissions, and enrollments (full-time and part-time) for fall cohorts.

### UrbanCollegeRequirements
**Rows:** 6,068  
Admission requirements and test score data including SAT/ACT percentiles (25th, 50th, 75th), open admissions policies, and required application materials.

### UrbanCollegeTuitions
**Rows:** 16,588  
Tuition and fee data by academic level (undergraduate, graduate) and residency status (in-state, out-of-state) with year-over-year percentage increases.

### UrbanCollegeTuitionProfessions
**Rows:** 1,498  
Professional program tuition for specialized fields (law, medicine, dentistry, veterinary, etc.) by residency status.

### UrbanCollegeTuitionVocations
**Rows:** 7,714  
Vocational and certificate program tuition by CIP code including program length, required hours, and enrollment information.

### UrbanCollegeRoomBoardAcademics
**Rows:** 10,166  
Room and board costs for academic programs by living arrangement (on-campus, off-campus with family, off-campus not with family) and student level.

### UrbanCollegeRoomBoardVocations
**Rows:** 4,118  
Room and board costs for vocational programs by living arrangement with associated living expenses.

### UrbanCollegeEnrollmentFtes
**Rows:** 17,937  
Full-time equivalent (FTE) enrollment data calculated from credit hours and contact hours by academic level (undergraduate, graduate).

### UrbanCollegeRetentions
**Rows:** 16,713  
Student retention rates tracking first-time, full-time students who return for their second year by full-time/part-time status.

### UrbanCollegeFinances
**Rows:** 5,696  
Comprehensive financial data including revenues, expenditures, assets, liabilities, endowment values, and functional expense categories (instruction, research, student services).

### UrbanCollegeStudentFacultyRatios
**Rows:** 5,571  
Student-to-faculty ratios calculated as FTE students divided by FTE instructional staff for measuring teaching intensity.

### UrbanCollegeFinancialAidLivings
**Rows:** 35,900  
Financial aid statistics by living arrangement and aid type showing number of students receiving aid and participation rates.

### UrbanCollegeFinancialAidTuitionTypes
**Rows:** 16,168  
Financial aid data segmented by tuition type (in-state, out-of-state, in-district) and cohort characteristics.

### UrbanCollegeFinancialAidUndergrads
**Rows:** 17,070  
Undergraduate financial aid data by aid type (grants, loans, work-study) including average amounts and student counts.

### UrbanCollegeFinancialAidFtfts
**Rows:** 59,763  
First-time, full-time student financial aid data by degree-seeking status, class level, and aid type with average amounts awarded.

### UrbanCollegeGraduation150s
**Rows:** 196,232  
150% graduation rates (6 years for bachelor's, 3 years for associate's) by demographic characteristics (race, gender) and cohort adjustments.

### UrbanCollegeGraduation200s
**Rows:** 4,741  
200% graduation rates (8 years for bachelor's, 4 years for associate's) providing extended completion timeframes for non-traditional students.

### UrbanCollegeGraduationAids
**Rows:** 37,036  
Graduation rates segmented by federal aid receipt type (Pell Grant recipients, subsidized loan recipients) and institution level.

### UrbanCollegeOutcomeMeasures
**Rows:** 88,421  
Outcome measures tracking degree completion, transfer, and enrollment status at 4, 6, and 8 years by student entry characteristics.

### UrbanCollegeCompleters
**Rows:** 237,880  
Program completers (graduates) by demographic characteristics (race, gender) and cohort year for completion analysis.

### UrbanCollegeAwardsCip2s
**Rows:** 4,149,840  
Awards conferred (degrees/certificates) by 2-digit CIP code, award level, race, gender, and major number for broad program analysis.

### UrbanCollegeAwardsCip6s
**Rows:** 9,011,490  
Awards conferred (degrees/certificates) by 6-digit CIP code providing detailed program-level completions by demographic characteristics.

### UrbanCollegeLibraries
**Rows:** 3,711  
Library statistics including collections (physical and electronic books, serials, media), expenditures, staff counts, and circulation data.

### UrbanCollegeSalariesInstructionals
**Rows:** 370,776  
Instructional staff salaries by academic rank (professor, associate, assistant, instructor), contract length (9-month, 11-month, 12-month), and gender.

### UrbanCollegeSalariesNonInstructionals
**Rows:** 111,510  
Non-instructional staff salaries by occupational category (administrators, support staff, librarians) with staff counts and total outlays.

---

## Peer College Data

We purchased a dataset of peer college comparisons from the Chronicle of Higher Education. This includes both IPEDS-defined peer groups as well as custom peer groups defined by the Chronicle.

### ChroniclePeerColleges
**Rows:** ~145,000  
Chronicle of Higher Education peer institution comparisons including IPEDS-defined and custom peer groups with comparative metrics (admissions rates, enrollment, graduation rates).

---

## Classification Systems

These tables represent fields of study (CIP) and occupations (SOC) as tracked by the U.S. government.

### CIPFamilies
**Rows:** ~61  
Classification of Instructional Programs (CIP) 2-digit family codes representing broad academic program areas (e.g., 01=Agriculture, 14=Engineering).

### CIPSubclasses
**Rows:** ~604  
CIP 4-digit subclass codes providing intermediate-level program classifications within families (e.g., 14.08=Civil Engineering).

### CIPCodes
**Rows:** ~10,649  
CIP 6-digit codes defining specific instructional programs with detailed definitions from the National Center for Education Statistics (2020 taxonomy).

### SOCCodes
**Rows:** 1,447  
Standard Occupational Classification (SOC) codes from the Bureau of Labor Statistics organizing occupations into a hierarchical structure (major, minor, broad, detailed groups).

### SocCipCrosswalks
**Rows:** 5,723  
SOC-to-CIP crosswalk mappings linking occupational classifications to related instructional programs for career pathway analysis.

### SOCExamples
**Rows:** 2,426  
Specific occupation examples for each SOC code illustrating the types of jobs classified under each occupational category.

### ONetOccupations
**Rows:** ~9,293  
O*NET occupation data providing comprehensive job information including titles, descriptions, and O*NET-SOC codes.

### ONetSocCrosswalks
**Rows:** ~4,574  
O*NET to SOC crosswalk mappings linking detailed O*NET occupation codes to standard SOC classifications.

### ONetAlternateTitles
**Rows:** ~34,445  
Alternative job titles for O*NET occupations capturing the diverse ways employers refer to similar positions.

### ONetSkills
**Rows:** ~67,807  
Skills data for occupations including importance ratings, level scores, confidence intervals, and measurement scales from O*NET surveys.

### ONetRelatedOccupations
**Rows:** ~9,230  
Related occupation linkages showing career progression pathways and alternative occupations organized by relatedness tiers.

---

## System Tables

### PersistentTasks
**Rows:** ~5
Task queue management system tracking background jobs (data imports, web crawling, AI processing) with status, completion timestamps, and error messages.

This is for internal processing by Peter. You will not need this table. 

---

## Data Format Notes

### CSV Specifications
- **Encoding:** UTF-8
- **Delimiter:** Comma (,)
- **Quoting:** Fields containing commas, quotes, or line breaks are quoted
- **NULL Values:** Empty fields (no value between delimiters)
- **Date Format:** ISO 8601 (`YYYY-MM-DDTHH:MM:SS.FFFZ`)
- **Binary Data:** Base64 encoded
- **Geography Columns:** Not included in this export (use `--include-geography` flag to export as WKT)

### Special Considerations

**Large Files:**
- `UrbanCollegeAwardsCip6s.csv` (1.02 GB) - Over 9 million award records (TRUNCATED to 100 rows)
- `UrbanCollegeAwardsCip2s.csv` (544 MB) - Over 4 million award records (TRUNCATED to 100 rows)
- Consider using specialized tools (Python pandas, R data.table, or database imports) for efficient processing

**Relational Integrity:**
- Foreign key relationships are preserved through ID columns
- Primary keys use Snowflake ID format (64-bit identifiers as strings)
- Join tables using matching column names (e.g., `UnitId` in UrbanColleges joins to `UnitId` in detail tables)

**Data Quality:**
- NULL values indicate missing or not applicable data
- -2 values typically indicate "Not applicable"
- 99 values in categorical fields typically indicate "Total" or aggregate records

---

## Data Sources

- **IPEDS (Integrated Postsecondary Education Data System):** U.S. Department of Education, National Center for Education Statistics
- **Urban Institute Education Data API:** College-level data aggregation
- **NCES Common Core of Data (CCD):** Public K-12 schools
- **Private School Survey (PSS):** Private K-12 schools
- **Chronicle of Higher Education:** Peer institution comparisons
- **Bureau of Labor Statistics:** SOC codes and CIP-SOC crosswalks
- **O*NET (Occupational Information Network):** U.S. Department of Labor occupation data
