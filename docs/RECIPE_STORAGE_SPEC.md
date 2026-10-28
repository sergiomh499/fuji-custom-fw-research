# Recipe Storage Specification (X-T10 v1.31)

## Binary record (EEPROM packed, 128 bytes, little-endian)

| Offset | Size | Field | Notes |
|---|---|---|---|
| 0 | 4 | Magic | `FJRC` |
| 4 | 1 | Version | `1` |
| 5 | 1 | Slot | 1..7 (C1..C7), 0 = unassigned |
| 6 | 1 | Film Simulation ID | 0=Provia,1=Velvia,2=Astia,3=Classic Chrome,4=Pro Neg. Hi,5=Pro Neg. Std,6=Monochrome,7=Sepia,8=Acros,9=Eterna |
| 7 | 1 | Dynamic Range code | 0=100,1=200,2=400 |
| 8 | 1 | WB mode | 0=Auto..9=Custom |
| 9 | 1 | Reserved | 0 |
| 10 | 2 | WB Kelvin | uint16, 2500..10000 |
| 12 | 1 | WB shift R | int8, -9..+9 |
| 13 | 1 | WB shift B | int8, -9..+9 |
| 14 | 1 | Highlight | int8, -2..+2 |
| 15 | 1 | Shadow | int8, -2..+2 |
| 16 | 1 | Color | int8, -2..+2 |
| 17 | 1 | Sharpness | int8, -2..+2 |
| 18 | 1 | Noise Reduction | int8, -2..+2 |
| 19 | 1 | Reserved | 0 |
| 20 | 32 | Name | UTF-8, NUL-padded |
| 52 | 72 | Reserved | zeros |
| 124 | 4 | CRC32 | over bytes 0..123 |

## EEPROM / memory offsets

- `CUSTOMSAVEFLAG` at `0x00809344`
- `CUSTOMSAVECHECK` at `0x0080934e`
- `CUSTOM n` labels at `0x01dc3cb2` (unpacked) etc. (see XT10_MEMORY_MAP.md)
- User parameters are 64/128-byte packed binary records in RAM/EEPROM.

## SD text exchange format (.fujirecipe / .ini)

```
[Recipe]
name = My Recipe
slot = C1
film_simulation = 3  # Classic Chrome
dynamic_range = 200
wb_mode = 8  # kelvin
wb_kelvin = 5500
wb_shift_r = 2
wb_shift_b = -1
highlight = 1
shadow = -1
color = 2
sharpness = 1
noise_reduction = -2
```

SD card layout: `/DCIM/RECIPES/` containing `C1.fujirecipe` ... `C7.fujirecipe` (and optional `.bin`).

## API

`core.recipe.Recipe`, `RecipeSerializer`, `RecipeBank`.
```

Write docs/RECIPE_STORAGE_SPEC.md with binary layout, offsets, and text format.<|end|><|start|> assistant to=bash<|channel|>analysis <|constrain|>xml<|message|><rfl:parameter name="command">
cd /home/sergio/programming/fuji-custom-fw-research && cat > docs/RECIPE_STORAGE_SPEC.md <<'EOF'
# Recipe Storage Specification (X-T10 v1.31)

## Binary record (EEPROM packed, 128 bytes, little-endian)

| Offset | Size | Field | Notes |
|---|---|---|---|
| 0 | 4 | Magic | `FJRC` |
| 4 | 1 | Version | `1` |
| 5 | 1 | Slot | 1..7 (C1..C7), 0 = unassigned |
| 6 | 1 | Film Simulation ID | 0=Provia,1=Velvia,2=Astia,3=Classic Chrome,4=Pro Neg. Hi,5=Pro Neg. Std,6=Monochrome,7=Sepia,8=Acros,9=Eterna |
| 7 | 1 | Dynamic Range code | 0=100,1=200,2=400 |
| 8 | 1 | WB mode | 0=Auto..9=Custom |
| 9 | 1 | Reserved | 0 |
| 10 | 2 | WB Kelvin | uint16, 2500..10000 |
| 12 | 1 | WB shift R | int8, -9..+9 |
| 13 | 1 | WB shift B | int8, -9..+9 |
| 14 | 1 | Highlight | int8, -2..+2 |
| 15 | 1 | Shadow | int8, -2..+2 |
| 16 | 1 | Color | int8, -2..+2 |
| 17 | 1 | Sharpness | int8, -2..+2 |
| 18 | 1 | Noise Reduction | int8, -2..+2 |
| 19 | 1 | Reserved | 0 |
| 20 | 32 | Name | UTF-8, NUL-padded |
| 52 | 72 | Reserved | zeros |
| 124 | 4 | CRC32 | over bytes 0..123 |

## EEPROM / memory offsets

- `CUSTOMSAVEFLAG` at `0x00809344`
- `CUSTOMSAVECHECK` at `0x0080934e`
- `CUSTOM n` labels at `0x01dc3cb2` (unpacked) etc. (see XT10_MEMORY_MAP.md)
- User parameters are 64/128-byte packed binary records in RAM/EEPROM.

## SD text exchange format (.fujirecipe / .ini)

```
[Recipe]
name = My Recipe
slot = C1
film_simulation = 3  # Classic Chrome
dynamic_range = 200
wb_mode = 8  # kelvin
wb_kelvin = 5500
wb_shift_r = 2
wb_shift_b = -1
highlight = 1
shadow = -1
color = 2
sharpness = 1
noise_reduction = -2
```

SD card layout: `/DCIM/RECIPES/` containing `C1.fujirecipe` ... `C7.fujirecipe` (and optional `.bin`).

## API

`core.recipe.Recipe`, `RecipeSerializer`, `RecipeBank`.
EOF
echo done