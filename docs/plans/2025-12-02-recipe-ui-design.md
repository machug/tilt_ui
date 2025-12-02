# Recipe Import UI Design

**Date:** 2025-12-02
**Status:** Approved
**Related Issue:** #32 (Implement Recipe Import UI for BeerXML files)
**Backend Status:** ✅ Complete (PR #27)

## Overview

Build frontend UI for BeerXML recipe import and management. Backend API is fully implemented and tested. This is a pure frontend task using existing endpoints.

## Goals

1. Enable users to upload BeerXML files through web UI
2. Browse and search imported recipes in a library view
3. View detailed recipe information with fermentation-focused layout
4. Integrate recipe selection into batch creation workflow
5. Create a distinctive "laboratory notebook" aesthetic that complements existing technical minimalism

## Design Direction: Industrial Laboratory Archive

### Aesthetic Identity

**Core Concept:** Scientific specimen archive meets brewing journal

BrewSignal's existing aesthetic is **refined technical minimalism** — dark zinc grays, Geist typeface, restrained blue accent. It prioritizes clarity and data density.

Recipe UI adds **warmth and character** while maintaining technical precision:

- **Typography**:
  - UI chrome: Geist (existing) for navigation, buttons, labels
  - Recipe names: **Crimson Pro** (serif) for warmth and editorial feel
  - Measurements: **JetBrains Mono** for technical precision

- **Color**:
  - Base: Existing dark zinc scale (`--gray-950` to `--gray-50`)
  - Recipe accent: **Amber `#f59e0b`** (warm contrast to blue monitoring accent)
  - Visual differentiation: Amber = recipes/planning, Blue = live monitoring/data

- **Layout**:
  - List view: Card grid (specimen boxes) — compact, scannable
  - Detail view: Laboratory notebook — sectioned, editorial
  - Import view: Large drop zone with generous negative space

- **Motion**:
  - File upload: Particle effect simulating grain/hop additions on drop
  - Card hover: Subtle lift with amber glow
  - Page transitions: Smooth fade with slight vertical shift (existing pattern)

### Visual References

- Brewfather's recipe detail (comprehensive ingredient lists, calculations)
- Scientific specimen labels (structured, hierarchical data)
- Laboratory notebooks (sectioned, annotated)
- Archival card catalogs (organized, browsable)

## Architecture

### Database: SQLite (Local)

**Decision:** Keep existing SQLite database on Raspberry Pi.

**Rationale:**
- Single-user fermentation monitoring (no multi-user auth needed)
- Recipe import is read-heavy (import once, reference many times)
- Zero network latency for 15-second Tilt readings
- No cloud dependencies (works offline)
- Simple backup (rsync SQLite file to Synology NAS)
- Backend already complete and tested with SQLite

**Not Choosing Cloud DB Because:**
- Latency: Round-trip to cloud adds delay to real-time monitoring
- Dependency: Internet outage breaks fermentation monitoring
- Cost: 5,760+ readings/day per Tilt could hit free tier limits
- Complexity: Auth, API keys, migration overhead
- Privacy: Recipes remain local

### Frontend Stack

- **Framework:** SvelteKit (existing)
- **Language:** TypeScript with Svelte 5 runes
- **Styling:** Inline `<style>` blocks with CSS variables
- **Fonts:**
  - Crimson Pro (Google Fonts) — recipe names
  - JetBrains Mono (Google Fonts) — measurements
  - Geist (existing) — UI chrome
- **API Client:** Existing `$lib/api.ts` patterns

## Routes

### 1. Recipe Import (`/recipes/import`)

**Purpose:** Upload BeerXML files

**Layout:**
```
┌─────────────────────────────────────────────────────┐
│ ← Back to Recipes                                   │
│                                                     │
│  Import Recipes from BeerXML                        │
│  Upload .xml files from Brewfather, BeerSmith, etc. │
│                                                     │
│  ┌─────────────────────────────────────────────┐   │
│  │                                             │   │
│  │         Drop BeerXML file here              │   │
│  │              or click to browse             │   │
│  │                                             │   │
│  │  📄 Supported: .xml (max 1MB)               │   │
│  └─────────────────────────────────────────────┘   │
│                                                     │
│  [After upload, shows preview of parsed recipes]    │
│                                                     │
│  Recipe Name: Sample Blonde Ale                     │
│  OG: 1.044  FG: 1.008  ABV: 4.7%                   │
│  Yeast: US-05 (18-22°C)                            │
│                                                     │
│  [ Cancel ]  [ Import Recipe ]                      │
└─────────────────────────────────────────────────────┘
```

**Features:**
- Drag-and-drop with visual feedback
- File validation (size, extension)
- BeerXML parsing preview before save
- Error handling for invalid XML
- Animated particle effect on drop (grain/hops visual)

**API:**
```typescript
POST /api/recipes/import
Content-Type: multipart/form-data
Body: { file: File }

Response: RecipeResponse[]
```

### 2. Recipe List (`/recipes`)

**Purpose:** Browse and search recipe library

**Layout:**
```
┌─────────────────────────────────────────────────────┐
│  Recipes (12)                    [ + Import Recipe] │
│  ┌──────────────┐  ┌──────────────┐                │
│  │ Search       │  │ Filter: All  │                │
│  └──────────────┘  └──────────────┘                │
│                                                     │
│  ┌──────────────────┐  ┌──────────────────┐       │
│  │ Blonde Ale       │  │ West Coast IPA   │       │
│  │ 18A • 4.7% ABV   │  │ 21A • 6.8% ABV   │       │
│  │ ▓░░░ 8.5 SRM    │  │ ▓▓░░ 12 SRM      │       │
│  │ 1.044 → 1.008    │  │ 1.065 → 1.012    │       │
│  │ US-05            │  │ WLP001           │       │
│  └──────────────────┘  └──────────────────┘       │
│                                                     │
│  [More recipe cards...]                             │
└─────────────────────────────────────────────────────┘
```

**Features:**
- Grid of recipe cards (specimen boxes)
- Each card shows:
  - Recipe name (Crimson Pro serif)
  - Style code + ABV
  - SRM color bar (visual)
  - OG → FG gravity range
  - Yeast strain
- Search by name/author
- Filter by style, type (Ale/Lager/Mead)
- Sort by created date (newest first)
- Click card → detail view
- Empty state with "Import your first recipe" CTA

**API:**
```typescript
GET /api/recipes?limit=50&offset=0
Response: RecipeResponse[]
```

### 3. Recipe Detail (`/recipes/[id]`)

**Purpose:** View complete recipe with fermentation focus

**Layout:**
```
┌─────────────────────────────────────────────────────┐
│ ← Back to Recipes              [ Edit ] [ Delete ]  │
│                                                     │
│ Sample Blonde Ale                                   │
│ American Blonde Ale (18A) • by Brewfather          │
│                                                     │
│ ┌─────────────────────────────────────────────────┐│
│ │ FERMENTATION PARAMETERS                         ││
│ │                                                 ││
│ │ Original Gravity    Final Gravity    ABV       ││
│ │ 1.044               1.008            4.7%      ││
│ │                                                 ││
│ │ Yeast: Safale US-05 (Fermentis)                ││
│ │ Temperature: 18-22°C                            ││
│ │ Attenuation: 81%                                ││
│ └─────────────────────────────────────────────────┘│
│                                                     │
│ ┌─────────────────────────────────────────────────┐│
│ │ STYLE GUIDELINES (BJCP 2021)                    ││
│ │                                                 ││
│ │ OG: 1.038-1.054      Color: 5.9-11.8 EBC       ││
│ │ FG: 1.008-1.013      IBU: 15-28                ││
│ └─────────────────────────────────────────────────┘│
│                                                     │
│ Batch Size: 23 L                                    │
│ Type: All Grain                                     │
│                                                     │
│ Notes: This is a sample recipe from Brewfather      │
│                                                     │
│ Created: Feb 11, 2019                              │
│                                                     │
│ [ Brew This Recipe ]                                │
└─────────────────────────────────────────────────────┘
```

**Features:**
- Fermentation-focused layout (OG/FG/yeast prominent)
- Minimize brewing details (ingredients hidden or collapsed)
- "Brew This Recipe" → `/batches/new?recipe_id={id}`
- Delete confirmation modal
- Shows style guideline ranges if style_id linked

**API:**
```typescript
GET /api/recipes/{id}
Response: RecipeResponse

DELETE /api/recipes/{id}
Response: { status: "deleted" }
```

### 4. Batch Form Integration

**Modify:** `/batches/new` and `BatchForm.svelte`

**Changes:**
- Add "Import from Recipe" section at top of form
- Recipe selector:
  - Search/filter recipes
  - Thumbnail preview cards
  - Click to select → auto-populate fields
- Auto-fill from selected recipe:
  - `name`: recipe.name
  - `measured_og`: recipe.og_target (as default)
  - Display yeast info for reference
- Allow manual override of all fields

**Flow:**
1. User clicks "New Batch"
2. Optional: Select recipe from library
3. Form pre-fills with recipe data
4. User adjusts as needed (actual measured OG, etc.)
5. Select device, set status
6. Create batch

## Component Breakdown

### `RecipeCard.svelte`

**Props:**
```typescript
interface Props {
  recipe: RecipeResponse;
  onClick?: () => void;
}
```

**Features:**
- Specimen box aesthetic (border, subtle shadow)
- Amber accent on hover
- SRM color gradient bar
- Truncate long names with ellipsis
- Clickable for navigation

### `RecipeImportZone.svelte`

**Props:**
```typescript
interface Props {
  onImport: (recipes: RecipeResponse[]) => void;
}
```

**Features:**
- Drag-and-drop file upload
- `<input type="file" accept=".xml">` fallback
- Particle animation on drop
- Loading spinner during upload/parse
- Error toast for invalid files
- Preview modal before saving

### `RecipeSelector.svelte`

**Props:**
```typescript
interface Props {
  selectedRecipeId?: number;
  onSelect: (recipe: RecipeResponse | null) => void;
}
```

**Features:**
- Compact recipe grid in modal/drawer
- Search bar at top
- "Clear Selection" button
- Emits selected recipe to parent

### `RecipeDetailView.svelte`

**Props:**
```typescript
interface Props {
  recipe: RecipeResponse;
}
```

**Features:**
- Laboratory notebook layout
- Sectioned information blocks
- Amber visual accents
- "Brew This Recipe" CTA button

## Typography Scale

```css
/* Recipe-specific typography */
@import url('https://fonts.googleapis.com/css2?family=Crimson+Pro:wght@400;600&family=JetBrains+Mono:wght@400;500&display=swap');

:root {
  --font-recipe-name: 'Crimson Pro', Georgia, serif;
  --font-measurement: 'JetBrains Mono', var(--font-mono);
}

/* Recipe name - serif, editorial */
.recipe-name {
  font-family: var(--font-recipe-name);
  font-size: 24px;
  font-weight: 600;
  letter-spacing: -0.02em;
}

/* Measurements - monospace, precise */
.recipe-measurement {
  font-family: var(--font-measurement);
  font-size: 14px;
  font-weight: 400;
  letter-spacing: -0.01em;
}
```

## Color Tokens

```css
:root {
  /* Recipe-specific accent (warm amber) */
  --recipe-accent: #f59e0b;
  --recipe-accent-hover: #d97706;
  --recipe-accent-muted: rgba(245, 158, 11, 0.15);

  /* SRM color visualization (examples) */
  --srm-pale: #f6e5a8;
  --srm-gold: #e5a840;
  --srm-amber: #d87a3a;
  --srm-brown: #8b4513;
  --srm-black: #1a0f0a;
}
```

## Navigation Integration

Add "Recipes" to main navigation in `+layout.svelte`:

```typescript
const navItems = [
  { href: '/', label: 'Dashboard', icon: 'dashboard' },
  { href: '/batches', label: 'Batches', icon: 'batches' },
  { href: '/recipes', label: 'Recipes', icon: 'recipes' }, // NEW
  { href: '/calibration', label: 'Calibration', icon: 'calibration' },
  { href: '/system', label: 'System', icon: 'system' },
];
```

## API Types (Add to `$lib/api.ts`)

Already exist from backend implementation:

```typescript
export interface RecipeResponse {
  id: number;
  name: string;
  author?: string;
  style_id?: string;
  type?: string; // "All Grain", "Extract", "Partial Mash"
  og_target?: number;
  fg_target?: number;
  yeast_name?: string;
  yeast_lab?: string;
  yeast_product_id?: string;
  yeast_temp_min?: number; // Celsius
  yeast_temp_max?: number; // Celsius
  yeast_attenuation?: number; // Percent
  ibu_target?: number;
  srm_target?: number;
  abv_target?: number;
  batch_size?: number; // Liters
  notes?: string;
  created_at: string;
}

// Add these helper functions
export async function fetchRecipes(limit = 50, offset = 0): Promise<RecipeResponse[]>;
export async function fetchRecipe(id: number): Promise<RecipeResponse>;
export async function importBeerXML(file: File): Promise<RecipeResponse[]>;
export async function deleteRecipe(id: number): Promise<void>;
```

## Motion & Interactions

### File Upload Animation

```css
@keyframes grain-fall {
  0% {
    transform: translateY(-100%) rotate(0deg);
    opacity: 0;
  }
  50% {
    opacity: 1;
  }
  100% {
    transform: translateY(100vh) rotate(360deg);
    opacity: 0;
  }
}

.grain-particle {
  position: absolute;
  width: 4px;
  height: 8px;
  background: var(--recipe-accent);
  border-radius: 2px;
  animation: grain-fall 2s ease-out forwards;
}
```

### Card Hover

```css
.recipe-card {
  transition: transform var(--transition), box-shadow var(--transition);
}

.recipe-card:hover {
  transform: translateY(-2px);
  box-shadow: 0 4px 12px var(--recipe-accent-muted);
}
```

## Accessibility

- All interactive elements keyboard navigable
- File upload accessible via click (no drag-only)
- ARIA labels for icons and actions
- Focus visible states with amber outline
- Semantic HTML (`<main>`, `<article>`, `<section>`)

## Error Handling

### File Upload Errors

- **File too large:** "File must be smaller than 1MB"
- **Invalid format:** "Please upload a .xml BeerXML file"
- **Parse error:** "Invalid BeerXML format: {error details}"
- **Network error:** "Upload failed. Please try again."

### Delete Confirmation

Modal with two-step confirmation:
1. "Are you sure you want to delete '{recipe.name}'?"
2. "This cannot be undone."
3. [ Cancel ] [ Delete Recipe ]

## Testing Strategy

### Manual Testing

- [ ] Upload valid BeerXML from Brewfather
- [ ] Upload invalid XML (should show error)
- [ ] Upload file >1MB (should reject)
- [ ] Browse recipe list, search/filter
- [ ] View recipe detail, navigate back
- [ ] Delete recipe with confirmation
- [ ] Create batch from recipe (auto-fill)
- [ ] Create batch without recipe (manual entry)

### Edge Cases

- [ ] No recipes (empty state)
- [ ] Recipe with missing fields (graceful fallback)
- [ ] Very long recipe names (truncate)
- [ ] Multiple recipes in single BeerXML file

## Implementation Checklist

- [ ] Add font imports to `app.css`
- [ ] Add recipe color tokens to CSS variables
- [ ] Add recipe API functions to `$lib/api.ts`
- [ ] Create `/recipes` route directory
- [ ] Create `/recipes/+page.svelte` (list)
- [ ] Create `/recipes/import/+page.svelte`
- [ ] Create `/recipes/[id]/+page.svelte` (detail)
- [ ] Create `RecipeCard.svelte` component
- [ ] Create `RecipeImportZone.svelte` component
- [ ] Create `RecipeSelector.svelte` component
- [ ] Update `BatchForm.svelte` with recipe selector
- [ ] Update navigation in `+layout.svelte`
- [ ] Test full flow: import → browse → create batch
- [ ] Update CHANGELOG.md
- [ ] Close issue #32

## Future Enhancements (Not in Scope)

- Recipe editing UI (currently delete + re-import)
- Recipe cloning/duplication
- Style browser with BJCP 2021 guidelines
- Recipe export to BeerXML
- Recipe sharing via URL
- Print-friendly recipe view
- Ingredient inventory tracking
- Recipe scaling calculator
- Mash profile visualization

## Success Criteria

✅ Users can upload BeerXML files via drag-and-drop or file picker
✅ Uploaded recipes display in searchable/filterable grid
✅ Recipe details show fermentation parameters prominently
✅ Batch creation form can auto-fill from selected recipe
✅ UI matches "laboratory archive" aesthetic with amber accents
✅ All interactions are smooth, accessible, and error-handled
✅ Issue #32 can be closed with complete implementation
