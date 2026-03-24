# CollegeSlugPreferences

## Overview

Entity representing a URL slug preference for a college or university.
            This table stores the preferred URL slug for each institution that will be used
            in the platform's URLs (e.g., https://www.ourdomain.com/schools/{slug}).
            
            Purpose:The goal is to create unique, meaningful URL slugs for colleges and universitiesthat are based on their domain names or other identifying characteristics.These slugs must be unique across the entire platform and are assigned basedon priority rankings to ensure popular schools get their preferred slugs.Key Features:- One row per school (UnitId is unique)- Slug field has unique constraint to prevent duplicates- Priority-based assignment system for conflict resolution- Denormalized institution data for performanceData Relationships:- UnitId references UrbanCollege.UnitId (IPEDS institutional identifier)- InstName and InstUrl are denormalized copies from UrbanCollege for performanceUsage Examples:- Harvard University → "harvard" (from harvard.edu)- University of Southern California → "usc" (from usc.edu)- ABC Beauty School → "abc-beauty-school" (from abc-beauty-school.com)

## Data Source

- **Source:** [To be documented]
- **Import Command:** [To be documented]
- **Last Updated:** 2025

## Record Count

**Total Records:** 6,090

## Schema

| Column Name | Data Type | Nullable | Max Length | Description |
|------------|-----------|----------|------------|-------------|
| `CreatedAt` | DateTimeOffset | No | - | Creation timestamp in UTC Records when this slug preference was determined and stored |
| `Id` | string | No | 32 | Primary key - Snowflake identifier (32 characters) Unique identifier for this slug preference record |
| `InstName` | string | No | 150 | Institution name - Copy of the official school name from UrbanCollege.InstName Denormalized for performance and to avoid joins in common queries Maximum length: 150 characters (matches UrbanCollege.InstName) This field is indexed for search performance |
| `InstUrl` | string | Yes | 500 | Institution URL - Copy of the school's website URL from UrbanCollege.InstUrl Denormalized for reference and debugging purposes This field is nullable as not all institutions have website URLs Maximum length: 500 characters (matches UrbanCollege.InstUrl) |
| `Slug` | string | No | 100 | URL slug - The unique URL-friendly identifier for this institution This is the value that will be used in URLs like https://www.ourdomain.com/schools/{slug} Constraints:- Maximum length: 100 characters- Unique constraint: No two schools can have the same slug- Indexed for fast lookup performance- Must be URL-safe (validated through ToSlug() extension method)Generation Rules:- First choice: Domain name without www/suffix (e.g., "harvard" from "harvard.edu")- Fallback: Domain + city/campus name (e.g., "abc-beauty-school-chicago")- LLM assistance: When domain-based approaches fail- All slugs are processed through ToSlug() extension for consistency |
| `UnitId` | int | No | - | IPEDS Unit ID - Foreign key reference to UrbanCollege.UnitId Links this slug preference to a specific college or university This field has a unique constraint - each school can have only one slug preference |

## Primary Key

- **Primary Key:** `Id`

## Indexes

- `IX_CollegeSlugPreferences_InstName` - Index on `InstName`
- `IX_CollegeSlugPreferences_Slug` - Index on `Slug` (Unique)
- `IX_CollegeSlugPreferences_UnitId` - Index on `UnitId` (Unique)

## Relationships

### Foreign Keys
- No foreign key relationships defined

## Usage Notes

### For Developers

- **Table Name:** `CollegeSlugPreferences`
- **Entity Class:** `Loader.Data.CollegeSlugPreference`
- **Record Count:** 6,090 rows

## CSV Export Notes

- **File:** `CollegeSlugPreferences.csv`
- **Rows:** 6,090
- **Encoding:** UTF-8
- **Format:** Standard CSV with header row

## See Also

- [Main README](../README.md)
- [Export CSV Documentation](../../Loader/Documentation/UserGuide/export-csv.md)

