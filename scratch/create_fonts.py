from pathlib import Path
from fontTools.fontBuilder import FontBuilder
from fontTools.pens.ttGlyphPen import TTGlyphPen
from fontTools.pens.t2CharStringPen import T2CharStringPen


def create_test_fonts():
    output_dir = Path("tests/fixtures/fonts")
    output_dir.mkdir(parents=True, exist_ok=True)

    # 1. Create valid.ttf
    fb_ttf = FontBuilder(unitsPerEm=1024, isTTF=True)

    # Define font names
    nameStrings = {
        "copyright": "Copyright (c) 2026",
        "familyName": "TestTTF",
        "styleName": "Regular",
        "uniqueFontIdentifier": "TestTTF Regular:2026",
        "fullName": "TestTTF Regular",
        "version": "Version 1.000",
        "psName": "TestTTF-Regular",
    }

    glyphs = {
        ".notdef": TTGlyphPen(None).glyph(),
        "space": TTGlyphPen(None).glyph(),
    }
    horizontalMetrics = {
        ".notdef": (512, 0),
        "space": (512, 0),
    }
    charMap = {32: "space"}

    fb_ttf.setupGlyphOrder([".notdef", "space"])
    fb_ttf.setupGlyf(glyphs)
    fb_ttf.setupHorizontalMetrics(horizontalMetrics)
    fb_ttf.setupHorizontalHeader()
    fb_ttf.setupNameTable(nameStrings)
    fb_ttf.setupCharacterMap(charMap)
    fb_ttf.setupOS2()
    fb_ttf.setupPost()
    fb_ttf.save(output_dir / "valid.ttf")
    print("Created valid.ttf")

    # 2. Create valid.otf (CFF-based)
    fb_otf = FontBuilder(unitsPerEm=1024, isTTF=False)

    nameStrings_otf = {
        "copyright": "Copyright (c) 2026",
        "familyName": "TestOTF",
        "styleName": "Regular",
        "uniqueFontIdentifier": "TestOTF Regular:2026",
        "fullName": "TestOTF Regular",
        "version": "Version 1.000",
        "psName": "TestOTF-Regular",
    }

    glyphs_otf = {
        ".notdef": T2CharStringPen(512, None),
        "space": T2CharStringPen(512, None),
    }
    # Need to draw something or close charstring pen
    # Wait, T2CharStringPen doesn't need much, let's just use empty ones
    glyphs_cff = {}
    for name, pen in glyphs_otf.items():
        pen.moveTo((0, 0))
        pen.lineTo((10, 0))
        pen.lineTo((5, 10))
        pen.closePath()
        glyphs_cff[name] = pen.getCharString()

    horizontalMetrics_otf = {
        ".notdef": (512, 0),
        "space": (512, 0),
    }
    charMap_otf = {32: "space"}

    fb_otf.setupGlyphOrder([".notdef", "space"])
    fb_otf.setupCFF(
        nameStrings_otf["psName"],
        {"FullName": nameStrings_otf["fullName"]},
        glyphs_cff,
        {},
    )
    fb_otf.setupHorizontalMetrics(horizontalMetrics_otf)
    fb_otf.setupHorizontalHeader()
    fb_otf.setupNameTable(nameStrings_otf)
    fb_otf.setupCharacterMap(charMap_otf)
    fb_otf.setupOS2()
    fb_otf.setupPost()
    fb_otf.save(output_dir / "valid.otf")
    print("Created valid.otf")

    # 3. Create corrupt.ttf (0 bytes)
    corrupt_path = output_dir / "corrupt.ttf"
    corrupt_path.write_bytes(b"")
    print("Created corrupt.ttf")


if __name__ == "__main__":
    create_test_fonts()
