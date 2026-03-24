# CollegeNamePreferences

## Overview

Entity representing a preferred institutional name for a college or university.
            This table stores curated, normalized names for institutions that provide consistency
            across our platform, replacing the raw unstructured InstName values from UrbanColleges
            with clean, professional names determined through AI-powered curation and review.
            
            Purpose:The UrbanColleges table contains InstName field with inconsistent naming conventionsfrom various data sources. This entity provides clean, normalized institutional namesthat follow consistent styling and formatting rules for display to end users.Curation Process:- AI Curator analyzes institution data and proposes normalized name- AI Reviewer evaluates curator's proposal against quality guidelines- Iterative refinement between curator and reviewer until approval- Only approved names are persisted to this tableKey Features:- One row per school (UnitId is unique)- Fallback to OriginalInstName if preferred name generation fails- Tracks original name for reference and comparison- Supports upsert operations for iterative improvementData Relationships:- UnitId references UrbanCollege.UnitId (IPEDS institutional identifier)- OriginalInstName is copy of UrbanCollege.InstName for reference

## Data Source

- **Source:** [To be documented]
- **Import Command:** [To be documented]
- **Last Updated:** 2025

## Record Count

**Total Records:** 6,090

## Schema

| Column Name | Data Type | Nullable | Max Length | Description |
|------------|-----------|----------|------------|-------------|
| `Id` | string | No | 32 | Primary key - Snowflake identifier (32 characters) Unique identifier for this name preference record |
| `OriginalInstName` | string | No | 150 | Original institution name - Copy of the raw name from UrbanCollege.InstName Preserved for reference, comparison, and fallback purposes Maximum length: 150 characters (matches UrbanCollege.InstName) |
| `PreferredInstName` | string | No | 100 | Preferred institution name - The curated, normalized name for display This is the clean, professional name determined through AI curation process that follows consistent styling and formatting guidelines Maximum length: 100 characters (concise but sufficient for institutional names) |
| `UnitId` | int | No | - | IPEDS Unit ID - Foreign key reference to UrbanCollege.UnitId Links this preferred name to a specific college or university This field has a unique constraint to ensure one preferred name per school |

## Primary Key

- **Primary Key:** `Id`

## Indexes

- `IX_CollegeNamePreferences_OriginalInstName` - Index on `OriginalInstName`
- `IX_CollegeNamePreferences_PreferredInstName` - Index on `PreferredInstName`
- `IX_CollegeNamePreferences_UnitId` - Index on `UnitId` (Unique)

## Relationships

### Foreign Keys
- `CollegeNamePreferences.`UnitId`` → `UrbanCollege.`UnitId``

## Usage Notes

### For Developers

- **Table Name:** `CollegeNamePreferences`
- **Entity Class:** `Loader.Data.CollegeNamePreference`
- **Record Count:** 6,090 rows

## CSV Export Notes

- **File:** `CollegeNamePreferences.csv`
- **Rows:** 6,090
- **Encoding:** UTF-8
- **Format:** Standard CSV with header row

## See Also

- [Main README](../README.md)
- [Export CSV Documentation](../../Loader/Documentation/UserGuide/export-csv.md)

