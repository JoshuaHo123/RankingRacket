# ONetAlternateTitles

## Overview

Entity representing alternate job titles associated with O*NET occupation codes.
            This dataset associates a variety of alternative job titles with the core O*NET Center codes,
            providing comprehensive coverage of how the same occupation may be titled across different
            organizations, industries, and contexts.
            
            Data Characteristics:- Approximately 50,000 rows in the complete dataset- Multiple alternate titles per occupation code (one-to-many relationship)- Includes both full alternate titles and abbreviated short titles- Sourced from various industry and occupational databasesUsage Examples:An O*NET code "11-1011.00" (Chief Executives) might have alternate titles like:- "Chief Executive Officer", "CEO" (short)- "Business Development Executive", "BD Executive" (short)- "Agency Owner", "Bureau Chief"Applications:- Job posting classification and matching- Resume parsing and occupation identification- Career guidance and job search optimization- Labor market analysis across different title conventions

## Data Source

- **Source:** [To be documented]
- **Import Command:** [To be documented]
- **Last Updated:** 2025

## Record Count

**Total Records:** 56,560

## Schema

| Column Name | Data Type | Nullable | Max Length | Description |
|------------|-----------|----------|------------|-------------|
| `AlternateTitle` | string | No | 200 | The alternate job title for this occupation. Examples: "Chief Executive Officer", "Business Development Executive", "Agency Owner" Content Characteristics:- Industry-specific variations of occupation titles- Formal and informal title variations- Regional or organizational naming conventions- Historical or legacy title variationsUsage:Primary field for job title matching, classification, and search functionality.Indexed for efficient text searches and pattern matching. This field is required and indexed for search performance. Maximum length: 200 characters to accommodate longer title variations. |
| `Code` | string | No | 16 | The O*NET-SOC occupation code this alternate title is associated with. Format: "XX-XXXX.XX" (e.g., "11-1011.00") Relationship:This field creates a many-to-one relationship where multiple alternatetitles can be associated with a single O*NET occupation code.Usage:Used to link alternate titles back to their canonical O*NET occupationfor comprehensive occupation analysis and job classification. This field is required, indexed for efficient lookups, and not unique since multiple titles can map to the same occupation code. Maximum length: 16 characters to accommodate O*NET code format. |
| `Id` | string | No | 32 | Unique identifier for this alternate title record. Generated using Snowflake algorithm for distributed system compatibility. |
| `ShortTitle` | string | Yes | 100 | Abbreviated or shortened version of the alternate title, if available. Examples: "CEO", "BD Executive", "BD Officer" Purpose:Provides commonly used abbreviations or shortened forms of job titlesthat are frequently used in job postings, business cards, and informal contexts.Usage Examples:- "Chief Executive Officer" → "CEO"- "Business Development Executive" → "BD Executive"- "Human Resources Manager" → "HR Manager"Data Quality:This field may be null or empty if no standard abbreviation existsfor the alternate title. Not all alternate titles have short forms. This field is nullable, indexed for search functionality when present. Maximum length: 100 characters to accommodate abbreviated titles. |
| `Year` | int | No | - | The year this alternate title data represents. Set to 2019 for the current dataset, will vary in future imports. Used for data versioning and temporal analysis. Indexed for efficient year-based queries. |

## Primary Key

- **Primary Key:** `Id`

## Indexes

- `IX_ONetAlternateTitles_AlternateTitle` - Index on `AlternateTitle`
- `IX_ONetAlternateTitles_Code` - Index on `Code`
- `IX_ONetAlternateTitles_ShortTitle` - Index on `ShortTitle`
- `IX_ONetAlternateTitles_Year` - Index on `Year`
- `IX_ONetAlternateTitles_Code_Year` - Index on `Code`, `Year`

## Relationships

### Foreign Keys
- No foreign key relationships defined

## Usage Notes

### For Developers

- **Table Name:** `ONetAlternateTitles`
- **Entity Class:** `Loader.Data.ONetAlternateTitle`
- **Record Count:** 56,560 rows

## CSV Export Notes

- **File:** `ONetAlternateTitles.csv`
- **Rows:** 56,560
- **Encoding:** UTF-8
- **Format:** Standard CSV with header row

## See Also

- [Main README](../README.md)
- [Export CSV Documentation](../../Loader/Documentation/UserGuide/export-csv.md)

