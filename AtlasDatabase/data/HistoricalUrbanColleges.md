# HistoricalUrbanColleges

## Overview

Entity representing historical college and university data from the Urban Institute Education Data API.
            This entity stores a subset of college information for institutions that existed in previous years
            but are no longer present in the current UrbanColleges table. This provides historical context
            for institutions that may have closed, merged, or otherwise ceased operations.
            
            Purpose:The HistoricalUrbanColleges table maintains records of colleges that existed in years 1980-2022but are not present in the current UrbanColleges table (which contains year 2023 data).This allows preservation of institutional memory for closed or merged institutions.Data Constraints:- Each UnitId appears only once across both UrbanColleges and HistoricalUrbanColleges tables- UnitId has a unique constraint to prevent duplicates- Records are populated by working backwards from 2022 to 1980- Only the most recent data for each historical institution is preserved- No institution should exist in both current and historical tables simultaneouslyData Source:API: https://educationdata.urban.org/api/v1/college-university/ipeds/directory/{year}/Years: 1980-2022 (excluding 2023 which is in UrbanColleges)

## Data Source

- **Source:** [To be documented]
- **Import Command:** [To be documented]
- **Last Updated:** 2025

## Record Count

**Total Records:** 16,295

## Schema

| Column Name | Data Type | Nullable | Max Length | Description |
|------------|-----------|----------|------------|-------------|
| `Address` | string | Yes | 100 | Street address or post office box - up to 100 characters Physical or mailing address of the institution as last reported May be null if address information was not provided or available |
| `City` | string | Yes | 50 | City location of institution - up to 50 characters City where the institution was located May be null if not reported in the source data |
| `CountyFips` | int | Yes | - | Federal Information Processing Standards county code Numeric identifier for the county within the state Combined with FIPS state code provides unique county identification May be null if not reported or outside standard FIPS coverage |
| `CountyName` | string | Yes | 50 | County name - up to 50 characters County where the institution was located Used for regional analysis and geographic clustering May be null if not reported or institution was in area without county structure |
| `DateClosed` | string | Yes | 20 | Date institution closed - up to 20 characters Date when the institution ceased operations (if applicable) Format varies in source data - may be year only, month/year, or full date Critical field for historical institutions as many will have closure dates May be null if institution was still active when last reported or date not provided |
| `Fips` | int | Yes | - | Federal Information Processing Standards state code Numeric code identifying the state (1-56, plus special codes) Used for standardized geographic identification and analysis May be null if institution was outside standard FIPS coverage |
| `Id` | string | No | 32 | Primary key - Snowflake identifier (32 characters) Unique identifier for this historical college record in our system |
| `InstControl` | InstitutionControl (enum) | Yes | - | Control of institution Public, private not-for-profit, or private for-profit Fundamental classification affecting funding, governance, and operations Used for comparative analysis and policy research May be null if not reported in the source data |
| `InstitutionLevel` | InstitutionLevel (enum) | Yes | - | Level of institution Educational level classification (2-year, 4-year, etc.) Indicates the highest level of degrees offered by the institution Critical for understanding institutional mission and student pathways May be null if not reported in the source data |
| `InstName` | string | No | 150 | Institution (entity) name - up to 150 characters Official name of the college or university as it appeared in IPEDS This is the primary identifier for the institution in human-readable form |
| `InstStatus` | InstitutionStatus (enum) | Yes | - | Status of institution Current operational status of the institution as last reported Important for historical analysis - many historical institutions will show closed, merged, or other non-active statuses May be null if status was not reported in the source data |
| `Latitude` | decimal | Yes | - | Latitude of institution - decimal(10,8) Geographic coordinate for institution location in decimal degrees Range: -90.0 to +90.0 (negative values represent southern hemisphere) Precision: Up to 8 decimal places for high accuracy May be null if coordinates were not available or reported |
| `Location` | Geography | Yes | - | Geographic location of the institution Geometry for spatial queries and mapping using NetTopologySuite Created from Latitude and Longitude coordinates when both are available Uses SRID 4326 (WGS84) coordinate reference system May be null if latitude/longitude coordinates are not available |
| `Longitude` | decimal | Yes | - | Longitude of institution - decimal(11,8) Geographic coordinate for institution location in decimal degrees Range: -180.0 to +180.0 (negative values represent western hemisphere) Precision: Up to 8 decimal places for high accuracy May be null if coordinates were not available or reported |
| `NewId` | int | Yes | - | Unit ID for merged schools Identifier for institutions that have merged with others Points to the UnitId of the institution this one merged into Important for tracking institutional continuity and successor relationships May be null if institution did not merge or merger information not available |
| `StateAbbr` | string | Yes | 2 | State abbreviation - 2 characters Two-letter postal code for the state where the institution was located Examples: "CA", "NY", "TX", "FL" May be null for institutions outside the US or if not reported |
| `UnitId` | int | No | - | Unit ID number - unique identifier for the institution Federal identifier used in IPEDS system This value is unique across both UrbanColleges and HistoricalUrbanColleges tables Range: Positive integers assigned by the Department of Education |
| `Year` | int | No | - | Academic year (fall semester) for this data record Represents the most recent year this institution appeared in the API before disappearing Range: 1980-2022 (institutions from these years not present in current UrbanColleges table) |
| `YearDeleted` | int | Yes | - | Year institution was deleted from Integrated Postsecondary Education Data System Year the institution was removed from IPEDS reporting Indicates when the institution was no longer tracked in federal databases Important for understanding data availability and institutional lifecycle May be null if institution was still in IPEDS when last reported |
| `Zip` | string | Yes | 10 | Zip code - up to 10 characters Postal code for the institution's address May include ZIP+4 format (e.g., "12345-6789") May be null if not reported or institution was outside US postal system |

## Primary Key

- **Primary Key:** `Id`

## Indexes

- `IX_HistoricalUrbanColleges_InstStatus` - Index on `InstStatus`
- `IX_HistoricalUrbanColleges_StateAbbr` - Index on `StateAbbr`
- `IX_HistoricalUrbanColleges_UnitId_Unique` - Index on `UnitId` (Unique)
- `IX_HistoricalUrbanColleges_Year` - Index on `Year`
- `IX_HistoricalUrbanColleges_YearDeleted` - Index on `YearDeleted`
- `IX_HistoricalUrbanColleges_State_Control_Level` - Index on `StateAbbr`, `InstControl`, `InstitutionLevel`

## Relationships

### Foreign Keys
- No foreign key relationships defined

## Usage Notes

### For Developers

- **Table Name:** `HistoricalUrbanColleges`
- **Entity Class:** `Loader.Data.HistoricalUrbanCollege`
- **Record Count:** 16,295 rows

## CSV Export Notes

- **File:** `HistoricalUrbanColleges.csv`
- **Rows:** 16,295
- **Encoding:** UTF-8
- **Format:** Standard CSV with header row

## See Also

- [Main README](../README.md)
- [Export CSV Documentation](../../Loader/Documentation/UserGuide/export-csv.md)

