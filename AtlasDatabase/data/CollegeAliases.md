# CollegeAliases

## Overview

Entity representing an alias name for a college or university.
            This table stores alternative names (aliases) for institutions that are commonly used
            by people when referring to the schools, such as "USC" for University of Southern California
            or "UCLA" for University of California Los Angeles.
            
            Purpose:The UrbanColleges table contains InstAlias field with inconsistent and unstructured data.This entity provides a clean, well-structured collection of aliases discovered throughOpenAI language model queries, allowing for better search and matching capabilities.Key Features:- One row per alias per school (multiple aliases per school are allowed)- Popularity ranking system for handling duplicate aliases across schools- Display ordering for consistent alias presentation- Unique constraint prevents duplicate aliases for the same schoolData Relationships:- UnitId references UrbanCollege.UnitId (IPEDS institutional identifier)- InstName is denormalized copy of UrbanCollege.InstName for performance

## Data Source

- **Source:** [To be documented]
- **Import Command:** [To be documented]
- **Last Updated:** 2025

## Record Count

**Total Records:** 1,186

## Schema

| Column Name | Data Type | Nullable | Max Length | Description |
|------------|-----------|----------|------------|-------------|
| `Alias` | string | No | 100 | Alias name - The alternative name discovered for this institution Examples: "USC", "UCLA", "Penn State", "UPenn", "Cal", "UCONN" Maximum length: 100 characters (configurable in entity configuration) |
| `DisplayOrder` | int | No | - | Display order for sorting multiple aliases for the same school Lower values are displayed first (0-based) Used for consistent ordering in user interfaces and reports |
| `Id` | string | No | 32 | Primary key - Snowflake identifier (32 characters) Unique identifier for this alias record |
| `InstName` | string | No | 150 | Institution name - Copy of the official school name from UrbanCollege.InstName Denormalized for performance and to avoid joins in common queries Maximum length: 150 characters (matches UrbanCollege.InstName) |
| `Popularity` | double | No | - | Popularity score in range 0.0 to 1.0 Used to rank aliases when multiple schools share the same alias name Scoring Guidelines:1.0 = Extremely well-known alias (USC, UCLA, MIT)0.7-0.9 = Well-known alias (Penn State, UPenn)0.3-0.6 = Moderately known alias0.1-0.2 = Lesser known or regional aliasThis helps determine which school is most likely intended whenusers search using an ambiguous alias name. |
| `UnitId` | int | No | - | IPEDS Unit ID - Foreign key reference to UrbanCollege.UnitId Links this alias to a specific college or university |

## Primary Key

- **Primary Key:** `Id`

## Indexes

- `IX_CollegeAliases_Alias` - Index on `Alias`
- `IX_CollegeAliases_InstName` - Index on `InstName`
- `IX_CollegeAliases_Popularity` - Index on `Popularity`
- `IX_CollegeAliases_UnitId` - Index on `UnitId`
- `IX_CollegeAliases_Alias_Popularity` - Index on `Alias`, `Popularity`
- `IX_CollegeAliases_UnitId_Alias` - Index on `UnitId`, `Alias` (Unique)

## Relationships

### Foreign Keys
- `CollegeAliases.`UnitId`` → `UrbanCollege.`UnitId``

## Usage Notes

### For Developers

- **Table Name:** `CollegeAliases`
- **Entity Class:** `Loader.Data.CollegeAlias`
- **Record Count:** 1,186 rows

## CSV Export Notes

- **File:** `CollegeAliases.csv`
- **Rows:** 1,186
- **Encoding:** UTF-8
- **Format:** Standard CSV with header row

## See Also

- [Main README](../README.md)
- [Export CSV Documentation](../../Loader/Documentation/UserGuide/export-csv.md)

