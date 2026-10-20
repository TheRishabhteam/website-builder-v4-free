"""
Design engine for the AI Website Builder.

Pure Python (no third-party imports) so it can be unit-tested anywhere.
 - make_brief():   picks fonts, corner style, motif and a layout "recipe" for every
                   section, different on every call (seeded, and avoids recent picks).
 - build_prompt(): turns a section request into (system, user) prompts for Claude.
 - sanitize_html(): removes anything the model should not output (external images,
                   wrapper tags, external scripts) and repairs truncated HTML.
"""
import random
import re

# --------------------------------------------------------------------------- #
# Fonts (all weights listed exist on Google Fonts)
# --------------------------------------------------------------------------- #
FONT_PAIRS = [
    dict(id="playfair-inter", head="Playfair Display", body="Inter", hs="Georgia,serif", bs="system-ui,sans-serif",
         q="family=Playfair+Display:ital,wght@0,400;0,700;0,900;1,400&family=Inter:wght@300;400;500;600;700",
         tags={"luxury", "trust", "classic", "editorial"}),
    dict(id="cormorant-jost", head="Cormorant Garamond", body="Jost", hs="Georgia,serif", bs="system-ui,sans-serif",
         q="family=Cormorant+Garamond:ital,wght@0,500;0,600;0,700;1,500&family=Jost:wght@300;400;500;600",
         tags={"luxury", "calm", "editorial"}),
    dict(id="dmserif-dmsans", head="DM Serif Display", body="DM Sans", hs="Georgia,serif", bs="system-ui,sans-serif",
         q="family=DM+Serif+Display&family=DM+Sans:wght@400;500;700",
         tags={"warm", "editorial", "friendly", "luxury"}),
    dict(id="poppins-inter", head="Poppins", body="Inter", hs="system-ui,sans-serif", bs="system-ui,sans-serif",
         q="family=Poppins:wght@500;600;700;800&family=Inter:wght@300;400;500;600",
         tags={"friendly", "clean", "trust", "energy"}),
    dict(id="spacegrotesk-inter", head="Space Grotesk", body="Inter", hs="system-ui,sans-serif", bs="system-ui,sans-serif",
         q="family=Space+Grotesk:wght@500;600;700&family=Inter:wght@300;400;500;600",
         tags={"tech", "bold", "clean"}),
    dict(id="syne-manrope", head="Syne", body="Manrope", hs="system-ui,sans-serif", bs="system-ui,sans-serif",
         q="family=Syne:wght@600;700;800&family=Manrope:wght@400;500;600;700",
         tags={"bold", "editorial", "tech"}),
    dict(id="fraunces-worksans", head="Fraunces", body="Work Sans", hs="Georgia,serif", bs="system-ui,sans-serif",
         q="family=Fraunces:wght@400;600;700;900&family=Work+Sans:wght@400;500;600",
         tags={"warm", "calm", "friendly", "editorial"}),
    dict(id="montserrat-opensans", head="Montserrat", body="Open Sans", hs="system-ui,sans-serif", bs="system-ui,sans-serif",
         q="family=Montserrat:wght@500;600;700;800&family=Open+Sans:wght@400;600",
         tags={"trust", "clean", "bold", "classic"}),
    dict(id="bebas-barlow", head="Bebas Neue", body="Barlow", hs="Impact,sans-serif", bs="system-ui,sans-serif",
         q="family=Bebas+Neue&family=Barlow:wght@400;500;600;700",
         tags={"bold", "energy"}),
    dict(id="lora-nunito", head="Lora", body="Nunito Sans", hs="Georgia,serif", bs="system-ui,sans-serif",
         q="family=Lora:wght@500;600;700&family=Nunito+Sans:wght@400;600;700",
         tags={"trust", "friendly", "calm", "classic"}),
    dict(id="outfit-jakarta", head="Outfit", body="Plus Jakarta Sans", hs="system-ui,sans-serif", bs="system-ui,sans-serif",
         q="family=Outfit:wght@500;600;700&family=Plus+Jakarta+Sans:wght@400;500;600;700",
         tags={"clean", "friendly", "tech", "energy"}),
    dict(id="marcellus-lato", head="Marcellus", body="Lato", hs="Georgia,serif", bs="system-ui,sans-serif",
         q="family=Marcellus&family=Lato:wght@400;700",
         tags={"classic", "luxury", "trust"}),
    dict(id="baskerville-source", head="Libre Baskerville", body="Source Sans 3", hs="Georgia,serif", bs="system-ui,sans-serif",
         q="family=Libre+Baskerville:wght@400;700&family=Source+Sans+3:wght@400;600",
         tags={"editorial", "classic", "trust"}),
]

RADII = [
    dict(id="soft", card="22px", btn="999px", img="22px"),
    dict(id="medium", card="14px", btn="12px", img="14px"),
    dict(id="sharp", card="4px", btn="4px", img="2px"),
    dict(id="pill", card="32px", btn="999px", img="32px"),
    dict(id="editorial", card="0px", btn="0px", img="0px"),
]

MOTIFS = [
    "thin hairline rules, small-caps letter-spaced labels and lots of whitespace",
    "soft blurred colour blobs, rounded shapes and gentle gradients",
    "bold geometric blocks, offset hard shadows and chunky numbering",
    "large editorial type, oversized numerals and asymmetric layouts",
    "glass panels, subtle noise-free gradients and glowing accents",
    "paper-like minimalism: fine 1px borders, muted tones, precise grid alignment",
    "organic arches and circles, warm tints and layered overlapping shapes",
    "diagonal cuts, accent stripes and strong contrast between dark and light blocks",
]

# --------------------------------------------------------------------------- #
# Industry knowledge
# --------------------------------------------------------------------------- #
INDUSTRIES = [
    (["dental"], dict(tags={"clean", "trust", "friendly"}, svc="Treatments", cta="Book an appointment",
                      mood="bright, clean, reassuring and modern; fresh whites, soft shadows, friendly confident tone")),
    (["spa", "aesthetic"], dict(tags={"luxury", "calm"}, svc="Treatments", cta="Book a session",
                                mood="serene and premium, soft light, generous whitespace")),
    (["wellness", "yoga"], dict(tags={"calm", "warm"}, svc="Programs & Classes", cta="Join a class",
                                mood="grounded, organic, breathing space, natural feel")),
    (["real estate"], dict(tags={"luxury", "clean", "trust"}, svc="Our Services", cta="Schedule a visit",
                           mood="aspirational, confident, architectural lines")),
    (["restaurant", "cafe"], dict(tags={"warm", "luxury"}, svc="Menu Highlights", cta="Reserve a table",
                                  mood="appetising, atmospheric, warm and inviting")),
    (["law"], dict(tags={"trust", "classic"}, svc="Practice Areas", cta="Book a consultation",
                   mood="authoritative, calm, serious but approachable")),
    (["gym", "fitness"], dict(tags={"bold", "energy"}, svc="Programs", cta="Start your trial",
                              mood="high energy, strong contrast, a sense of motion")),
    (["education", "coaching"], dict(tags={"friendly", "clean", "trust"}, svc="Courses", cta="Enquire now",
                                     mood="encouraging, bright, well structured")),
    (["ecommerce"], dict(tags={"clean", "bold"}, svc="Shop Categories", cta="Shop now",
                         mood="crisp, product-first retail with clear calls to action")),
    (["interior"], dict(tags={"editorial", "luxury", "warm"}, svc="Our Services", cta="Book a design consultation",
                        mood="refined, material-rich, editorial")),
    (["photography"], dict(tags={"editorial", "bold"}, svc="Packages", cta="Check availability",
                           mood="visual-first, gallery-led, artistic")),
    (["travel"], dict(tags={"warm", "energy"}, svc="Popular Packages", cta="Plan my trip",
                      mood="adventurous, colourful, inviting")),
    (["hospital"], dict(tags={"trust", "clean"}, svc="Departments & Services", cta="Book an appointment",
                        mood="caring, credible and calm")),
    (["accounting", "ca "], dict(tags={"trust", "classic"}, svc="Our Services", cta="Talk to an expert",
                                 mood="credible, orderly, no fluff")),
    (["news", "magazine"], dict(tags={"editorial", "classic"}, svc="Sections", cta="Subscribe",
                                mood="editorial, typographic, information-dense but clean")),
    (["fashion"], dict(tags={"editorial", "luxury", "bold"}, svc="Collections", cta="Visit the boutique",
                       mood="stylish, high-contrast, lookbook feel")),
    (["digital marketing"], dict(tags={"bold", "tech"}, svc="Services", cta="Book a strategy call",
                                 mood="modern, sharp, data-driven")),
    (["hotel", "resort"], dict(tags={"luxury", "warm"}, svc="Rooms & Experiences", cta="Check availability",
                               mood="hospitality, elegant, inviting")),
    (["salon", "beauty", "parlour"], dict(tags={"luxury", "friendly"}, svc="Our Services", cta="Book your slot",
                                          mood="glamorous, polished, confident")),
    (["construction"], dict(tags={"bold", "trust"}, svc="What We Build", cta="Request a quote",
                            mood="solid, structural, dependable")),
]
DEFAULT_INDUSTRY = dict(tags={"clean", "trust", "friendly"}, svc="Our Services", cta="Get in touch",
                        mood="modern, trustworthy and welcoming")

STYLE_PREFS = {
    "luxury": {"luxury", "editorial"},
    "clean": {"clean", "trust"},
    "bold": {"bold", "energy", "tech"},
    "warm": {"warm", "friendly"},
    "editorial": {"editorial", "classic"},
}


def industry_profile(bt):
    low = (bt or "").lower() + " "
    for keys, prof in INDUSTRIES:
        if any(k in low for k in keys):
            return prof
    return DEFAULT_INDUSTRY


# --------------------------------------------------------------------------- #
# Layout recipes.  img: "none" (no photos needed) | "opt" (works with or without)
#                       | "req" (needs at least `min` photos of that kind)
# --------------------------------------------------------------------------- #
HERO = [
    dict(id="cinematic_overlay", img="req", min=1, tone="dark", fit={"luxury", "warm", "bold", "clean"},
         text="Full-viewport cinematic hero (min-height:100vh; top padding >=120px because the nav is fixed). "
              "Background: {{IMG:hero1}} as cover, with a layered dark gradient overlay (heavier at the bottom). Content centred: "
              "a small italic tagline in var(--fh), a very large h1 (clamp(40px,7vw,84px)), a short hairline divider in var(--a), "
              "one sentence of subtext, then the primary WhatsApp CTA and a secondary 'Our Services' outline CTA. "
              "At the very bottom a frosted-glass strip (backdrop-filter:blur) holds 3-4 trust points (icon + short text; true facts or benefit phrases only)."),
    dict(id="split_panel", img="req", min=1, tone="dark", fit={"clean", "trust", "friendly", "luxury"},
         text="50/50 split hero, min-height:100vh. LEFT: solid var(--bg) panel with an eyebrow badge that has a pulsing dot, the h1, "
              "subtext, two CTAs and a row of trust chips. RIGHT: {{IMG:hero1}} full-height (cover) with a rounded inner frame offset by a "
              "thin accent outline, plus one small floating card overlapping the image edge (use the Google rating from FACTS if given, "
              "otherwise a 'Book on WhatsApp' mini card). On mobile the image goes on top (height 46vh) and text below."),
    dict(id="slider_fullscreen", img="req", min=2, tone="dark", fit={"luxury", "warm", "energy", "bold", "clean"},
         text="Fullscreen FADE slider hero using the component <div class='wb-slider' data-mode='fade' data-autoplay='6000'>. "
              "One slide per available hero image (use only the hero keys listed under IMAGES, up to 3). Every slide: min-height:100vh, "
              "its photo as cover background with a dark gradient overlay, and its OWN short headline + one-line subtext "
              "(slide 1 = brand promise with the only <h1>, other slides use <h2> style text about services / booking). "
              "The CTA buttons are repeated on each slide. Top padding >=120px for the fixed nav."),
    dict(id="bold_type", img="none", tone="dark", fit={"bold", "energy", "tech", "editorial"},
         text="Typographic hero with NO photos. Background var(--bg) with big geometric shapes / subtle grid lines in accent colour at low opacity. "
              "Giant uppercase h1 (clamp(48px,9vw,120px), tight line-height, weight 800-900) where one key word is outlined "
              "(-webkit-text-stroke:2px var(--a); color:transparent) or filled with var(--gr). Left-aligned, short subtext, one solid CTA + one text link. "
              "At the bottom, a full-width infinite horizontal marquee strip (CSS keyframes) repeating the service names separated by small icons."),
    dict(id="light_gradient_center", img="none", tone="light", fit={"clean", "friendly", "trust", "tech", "calm"},
         text="Light, airy hero with NO photos. White background with a soft mesh of 2-3 large blurred radial gradients in var(--p)/var(--a) at ~12-18% opacity. "
              "Centred layout: pill eyebrow badge, h1 (clamp(36px,6vw,72px)) with one word filled by var(--gr) via background-clip:text, subtext, two rounded CTAs. "
              "Below, a row of floating rounded 'chips' each with an icon and a service name (from the SERVICES list) with a gentle float animation. "
              "Hero text is dark (var(--td)). Leave >=110px top padding for the fixed nav."),
    dict(id="editorial_collage", img="opt", min=1, tone="light", fit={"editorial", "luxury", "warm", "calm", "friendly"},
         text="Two-column editorial hero on a warm light background. LEFT: eyebrow label, big serif h1, paragraph, CTAs, small trust row. "
              "RIGHT: a staggered collage of 1-3 images (use hero keys listed under IMAGES) inside arch-shaped / rounded frames with overlapping offsets and a "
              "decorative circle outline; if no hero photo is listed, build the collage from gradient shapes with large icons instead. "
              "Dark text. On mobile stack and show only the largest frame."),
    dict(id="luxury_minimal", img="req", min=1, tone="dark", fit={"luxury", "calm", "classic", "editorial"},
         text="Ultra-minimal luxury hero. {{IMG:hero1}} as cover with a 55% dark overlay and soft vignette. Centred: letter-spaced uppercase brand line, "
              "a LIGHT-weight (300) italic h1 with generous letter-spacing, a thin hairline in var(--a), one short sentence, and two outline buttons. "
              "A tiny animated scroll indicator at the bottom centre. Lots of negative space; no badges, no chips."),
    dict(id="diagonal_split", img="req", min=1, tone="dark", fit={"bold", "energy", "trust", "tech", "classic"},
         text="Dark hero with a diagonal image panel: text on the left over var(--bg); on the right {{IMG:hero1}} clipped with clip-path:polygon(18% 0,100% 0,100% 100%,0 100%) "
              "and an accent stripe following the diagonal edge. h1 clamp(38px,6vw,76px), subtext, 2 CTAs, and 3 compact fact tiles (icon + short label) under the buttons. "
              "On mobile the image becomes a banner above the text with a straight bottom edge."),
    dict(id="fact_cards", img="none", tone="dark", fit={"trust", "clean", "classic", "bold", "tech"},
         text="Dark hero WITHOUT photos. LEFT: eyebrow, h1, subtext, CTAs. RIGHT: a 2x2 grid of glass 'fact cards' (icon, short bold line, tiny caption). "
              "Use real numbers only from FACTS (Google rating / review count / years if stated); otherwise use benefit cards (e.g. 'Easy WhatsApp booking', 'Friendly expert team') without numbers. "
              "Soft glowing radial gradients behind the cards."),
    dict(id="arch_frame", img="req", min=1, tone="light", fit={"calm", "warm", "luxury", "friendly", "editorial"},
         text="Warm light hero. Centred text column (eyebrow, h1, subtext, CTAs) and beneath it one large ARCH-shaped image of {{IMG:hero1}} "
              "(border-radius:999px 999px 0 0, height ~46vh, max-width 760px) bleeding into the bottom edge, flanked by two small floating round badges (icon + 2-3 words). "
              "Warm tinted background using var(--lt). Dark text."),
]

SERVICES = [
    dict(id="photo_cards_grid", img="req", min=3, fit={"clean", "friendly", "luxury", "warm", "trust"},
         text="Responsive grid (auto-fit minmax(260px,1fr)) of photo cards. Each card: image on top (aspect-ratio 4/3, cover, zoom on hover) using that service's {{IMG:svcN}}, "
              "title, one-line description and an 'Enquire' WhatsApp link with the service pre-filled. A service without a photo gets a same-ratio gradient block with a large icon."),
    dict(id="slider_cards", img="opt", min=1, fit={"friendly", "luxury", "energy", "warm", "clean"},
         text="Section heading on the left and prev/next controls handled by the slider. A wb-slider (data-mode='slide' data-per-view='3' data-gap='22') of service cards: photo header "
              "(or gradient+icon if no photo), title, one-line description, 'Enquire' link. Cards have var(--rc) radius and soft shadow."),
    dict(id="icon_grid_cards", img="none", fit={"clean", "trust", "friendly", "classic", "tech"},
         text="3-column grid of icon cards: gradient icon tile, small index number in the corner, title, description, 'Learn more / Enquire' link. "
              "Accent top border that grows on hover and a subtle lift. No photos."),
    dict(id="dark_glass", img="opt", min=1, tone="dark", fit={"bold", "tech", "luxury", "energy"},
         text="Dark section (var(--bg)) with 2 big blurred colour glows behind. Glass cards (rgba(255,255,255,.07), backdrop-filter:blur(14px), 1px rgba(255,255,255,.14) border). "
              "If a service has a photo ({{IMG:svcN}}) use it as a faint blended card background or small rounded thumbnail; otherwise an accent-coloured icon."),
    dict(id="numbered_editorial", img="opt", min=1, fit={"editorial", "luxury", "classic", "bold"},
         text="Two-column editorial layout. LEFT (sticky on desktop): eyebrow, big h2, short intro and a CTA. RIGHT: a list of rows separated by hairlines: huge outline numerals 01, 02..., "
              "service name, one-line description, arrow icon. On row hover the row highlights in var(--a) and, if that service has a photo, a small rounded thumbnail slides in on the right."),
    dict(id="alternating_rows", img="req", min=2, fit={"editorial", "luxury", "warm", "calm", "trust"},
         text="Zig-zag rows (max 4 services with photos get a full row: big image {{IMG:svcN}} + text block with number, title, 2-sentence description, CTA); alternate image left/right. "
              "Any remaining services appear in a compact chip/list row at the end."),
    dict(id="tabs_showcase", img="opt", min=1, fit={"clean", "tech", "trust", "friendly", "luxury"},
         text="Tabbed showcase using the wb-tabs component: a vertical list of service buttons on the left (icon + name), and on the right a large panel per service with its photo "
              "({{IMG:svcN}}) or a gradient+icon art block, a heading, a 2-sentence description, 3 short bullet points and an 'Enquire on WhatsApp' button. On mobile the tab list becomes a horizontally scrollable pill row above the panel."),
    dict(id="minimal_list_grid", img="none", fit={"calm", "classic", "editorial", "clean", "trust"},
         text="Borderless minimalist 3-column list: small line icon, service name, short description, tiny 'Enquire' link; thin hairline dividers between rows; on hover a 3px accent bar grows on the left. No photos, lots of whitespace."),
    dict(id="bento_grid", img="opt", min=1, fit={"bold", "tech", "luxury", "editorial", "energy"},
         text="Bento grid (CSS grid with varied spans): the first service is a large featured tile (photo {{IMG:svcN}} with gradient overlay if available), others are mixed 1x1 / 2x1 tiles "
              "alternating light, dark (var(--bg)) and accent (var(--gr)) tiles with icon, title and a one-line description. Collapses to a single column on phones."),
]

ABOUT = [
    dict(id="split_image_checks", img="opt", min=1, fit={"clean", "trust", "friendly", "classic", "warm"},
         text="Two columns: image (about photo {{IMG:about}}) with a floating badge card overlapping a corner, and text: eyebrow, h2, paragraph (from USP / facts), 4 check-mark points with small gradient circles, and a CTA. "
              "If no about photo is listed, replace the image with a layered gradient/pattern panel with a large icon."),
    dict(id="overlap_banner", img="opt", min=1, fit={"luxury", "editorial", "warm", "trust"},
         text="A wide banner image ({{IMG:about}}, height ~420px, rounded) with a white content card overlapping its bottom-left over the image: eyebrow, h2, paragraph, and a row of 2-3 fact/benefit highlights (numbers only if in FACTS). "
              "If there is no about photo use a rich gradient banner with decorative shapes."),
    dict(id="centered_story", img="none", fit={"calm", "luxury", "classic", "editorial", "clean"},
         text="Centred narrow story block: eyebrow, large statement-style h2, a paragraph, then three 'pillars' in a row (icon, short title, one sentence). A thin accent line above. No photos."),
    dict(id="timeline_values", img="none", fit={"trust", "classic", "tech", "bold", "clean"},
         text="Left column: eyebrow, h2, paragraph and CTA. Right column: a vertical timeline (line + dots) with 4 steps called 'Our approach' (short title + one sentence each). No invented dates or numbers. No photos."),
    dict(id="mosaic_decor", img="opt", min=1, fit={"warm", "friendly", "calm", "luxury", "editorial"},
         text="Text on one side. On the other, the about photo ({{IMG:about}}) cropped in a rounded/arch shape with decorative elements: an offset outline frame, a dotted pattern square and a circle in var(--a). "
              "If there is no photo use a gradient shape with a big icon."),
    dict(id="dark_feature", img="opt", min=1, tone="dark", fit={"bold", "tech", "energy", "luxury", "classic"},
         text="Dark section (var(--bg)): large headline spanning 2 columns, a paragraph, 3 key points with accent icons, and (if listed) the about image ({{IMG:about}}) as a tall rounded image with an accent glow. CTA button in var(--gr)."),
]

PROCESS = [
    dict(id="steps_horizontal", img="none", fit={"clean", "trust", "friendly", "tech", "classic"},
         text="Horizontal 4-step process: numbered circles joined by a dashed line, title and one sentence each; steps stack vertically on mobile. Steps should be the natural journey for this business type (e.g. enquire -> consult -> service -> follow-up)."),
    dict(id="why_choose_grid", img="none", fit={"clean", "trust", "bold", "friendly", "warm"},
         text="'Why choose us' grid of 6 benefit tiles (icon, title, one sentence) in a 3x2 grid; tiles are tinted, lift on hover, one tile is highlighted with var(--gr). Benefits must be generic and grounded in the USP/facts given."),
    dict(id="vertical_timeline", img="none", fit={"editorial", "classic", "luxury", "calm"},
         text="Centre-line vertical timeline of 4-5 steps alternating left/right on desktop (single column on mobile), with numbered nodes on the line and short descriptive text."),
    dict(id="split_steps", img="none", fit={"bold", "tech", "energy", "luxury"},
         text="Dark split: left sticky heading + intro + CTA; right stacked cards for 4 steps with huge faded numerals behind the text."),
]

GALLERY = [
    dict(id="slider_cards", img="req", min=3, fit={"friendly", "luxury", "warm", "clean", "energy"},
         text="wb-slider (data-mode='slide' data-per-view='3' data-gap='18' data-autoplay='4500') of rounded images (aspect-ratio 4/5, cover) with a soft caption gradient on hover. Each <img> has data-lightbox. Use every gallery key listed."),
    dict(id="masonry_columns", img="req", min=3, fit={"editorial", "luxury", "warm", "bold"},
         text="CSS-columns masonry (columns:3 desktop / 2 tablet / 1 phone, gap 14px) of all listed gallery images with natural heights, rounded corners, a hover overlay with a zoom icon. Each <img> has data-lightbox."),
    dict(id="bento_gallery", img="req", min=4, fit={"bold", "tech", "editorial", "luxury"},
         text="Bento gallery using CSS grid with varied row/column spans (one large 2x2 tile, one wide, rest square) over the listed images; hover zoom; each <img> has data-lightbox. Fill any extra cells by repeating nothing - just adjust spans to the number of images."),
    dict(id="filmstrip_slider", img="req", min=2, fit={"luxury", "calm", "classic", "warm", "editorial"},
         text="One large 16:9 hero-style slider (wb-slider data-mode='fade' data-autoplay='5000') showing one image at a time with a caption bar, arrows and dots. Each <img> has data-lightbox. Centre heading above."),
    dict(id="grid_lightbox", img="req", min=1, fit={"clean", "trust", "friendly", "classic", "energy"},
         text="Uniform 4-column grid (2 on tablet, 1-2 on phone) of square images with rounded corners, hover zoom and a centred zoom icon overlay. Each <img> has data-lightbox."),
    dict(id="polaroid_scatter", img="req", min=2, fit={"friendly", "warm", "editorial", "energy"},
         text="Polaroid-style cards: white frame with thick bottom caption area, slightly rotated alternately (-3deg / 2deg / -1deg...), straightening on hover, on a soft tinted background. Each <img> has data-lightbox."),
]

TESTIMONIALS = [
    dict(id="slider_cards", img="none", fit={"friendly", "clean", "luxury", "warm", "trust"},
         text="wb-slider (data-mode='slide' data-per-view='3' data-gap='22') of review cards: stars, quote, initial-avatar circle (gradient), name, small source line."),
    dict(id="big_quote_slider", img="none", tone="dark", fit={"luxury", "editorial", "classic", "calm", "bold"},
         text="Dark section with a single large quote at a time: wb-slider data-mode='fade' data-autoplay='7000'. Giant decorative quote mark in var(--a), quote in var(--fh) (clamp(20px,3vw,34px)), name + source below, stars. Centred."),
    dict(id="grid_cards", img="none", fit={"clean", "trust", "classic", "tech", "friendly"},
         text="3-column grid of white review cards with a coloured top border, large quote glyph, stars, quote, avatar initial, name, source line."),
    dict(id="featured_plus_stack", img="none", fit={"editorial", "bold", "luxury", "trust"},
         text="Asymmetric layout: one large featured review card on the left (gradient background var(--gr), white text, big quote) and two smaller stacked cards on the right."),
    dict(id="marquee_cards", img="none", fit={"energy", "bold", "tech", "friendly"},
         text="Two rows of compact review cards scrolling in opposite directions as infinite CSS marquees (pause on hover, reduced-motion safe). Cards: stars, short quote, name."),
    dict(id="masonry_quotes", img="none", fit={"warm", "friendly", "editorial", "calm"},
         text="CSS-columns masonry of review cards of different lengths with soft tinted backgrounds, rounded corners, stars, quote, name."),
]

FAQ = [
    dict(id="accordion_split", img="none", fit={"clean", "trust", "classic", "friendly"},
         text="Two columns: LEFT eyebrow, h2, short text and a WhatsApp CTA card ('Still have questions?'). RIGHT: accordion built with native <details><summary> elements (animated chevron, hairline separators)."),
    dict(id="accordion_cards", img="none", fit={"bold", "tech", "luxury", "energy", "editorial"},
         text="Centred heading, then a 2-column grid of <details> cards (each a rounded card with plus/minus icon that rotates). First item open."),
    dict(id="numbered_accordion", img="none", fit={"editorial", "classic", "calm", "luxury", "warm"},
         text="Single centred column of <details> rows with big numerals 01, 02, ... on the left, hairline dividers and a subtle background tint when open."),
]

RECIPES = {
    "hero": HERO, "services": SERVICES, "about": ABOUT, "process": PROCESS,
    "gallery": GALLERY, "testimonials": TESTIMONIALS, "faq": FAQ,
}
IMG_KIND = {"hero": "hero", "services": "svc", "about": "about", "gallery": "gal"}
PREFIX = {"hero": "hr", "services": "sv", "about": "ab", "process": "pr", "gallery": "gl",
          "testimonials": "ts", "faq": "fq"}
ID_OF = {"hero": "home", "services": "services", "about": "about", "process": "process",
         "gallery": "gallery", "testimonials": "testimonials", "faq": "faq"}
SECTION_ORDER = ["services", "about", "process", "gallery", "testimonials", "faq"]
TONE_STYLE = {
    "dark": "dark background: background:var(--bg); light text (#fff / rgba(255,255,255,.72)); accents in var(--a)",
    "light": "white background; text var(--td), muted text var(--tm)",
    "tint": "tinted background: background:var(--lt); text var(--td), muted text var(--tm)",
}


# --------------------------------------------------------------------------- #
# Brief
# --------------------------------------------------------------------------- #
def _weighted_pick(rnd, items, weights):
    total = sum(weights)
    if total <= 0:
        return rnd.choice(items)
    return rnd.choices(items, weights=weights, k=1)[0]


def _pick_recipe(rnd, section, count, ind_tags, pref_tags, avoid):
    cands, weights = [], []
    for r in RECIPES[section]:
        kind = r["img"]
        if kind == "req" and count < r.get("min", 1):
            continue
        w = 1.0 + 1.0 * len(r["fit"] & ind_tags) + 3.0 * len(r["fit"] & pref_tags)
        if kind == "none" and count > 0:
            w *= 0.55           # we have photos: prefer layouts that show them
        if kind == "req" and count > 0:
            w *= 1.25
        if "%s:%s" % (section, r["id"]) in avoid:
            w *= 0.08           # used recently: strongly avoid repeating
        cands.append(r)
        weights.append(w)
    if not cands:               # safety net: anything without a hard photo requirement
        cands = [r for r in RECIPES[section] if r["img"] != "req"] or RECIPES[section]
        weights = [1] * len(cands)
    return _weighted_pick(rnd, cands, weights)


def make_brief(p):
    try:
        seed = int(p.get("seed"))
    except (TypeError, ValueError):
        seed = random.randrange(1 << 30)
    rnd = random.Random(seed)
    prof = industry_profile(p.get("bt"))
    ind_tags = set(prof["tags"])
    pref_tags = set()
    for k in str(p.get("style_pref") or "").split(","):
        pref_tags |= STYLE_PREFS.get(k.strip(), set())
    avoid = set(str(a) for a in (p.get("avoid") or []))
    counts = p.get("img_counts") or {}
    sections = [s for s in (p.get("sections") or SECTION_ORDER) if s in RECIPES and s != "hero"]

    # fonts
    fw = []
    for f in FONT_PAIRS:
        w = 1.0 + 1.0 * len(f["tags"] & ind_tags) + 3.0 * len(f["tags"] & pref_tags)
        if "font:%s" % f["id"] in avoid:
            w *= 0.08
        fw.append(w)
    font = _weighted_pick(rnd, FONT_PAIRS, fw)

    radius = _weighted_pick(rnd, RADII, [0.08 if ("radius:%s" % r["id"]) in avoid else 1.0 for r in RADII])
    motif = rnd.choice([m for m in MOTIFS if ("motif:%d" % MOTIFS.index(m)) not in avoid] or MOTIFS)

    recipes = {}
    hero = _pick_recipe(rnd, "hero", int(counts.get("hero", 0) or 0), ind_tags, pref_tags, avoid)
    recipes["hero"] = hero["id"]
    tones = {"hero": hero.get("tone", "dark")}
    for s in sections:
        cnt = int(counts.get(IMG_KIND.get(s, ""), 0) or 0)
        r = _pick_recipe(rnd, s, cnt, ind_tags, pref_tags, avoid)
        recipes[s] = r["id"]
        if r.get("tone"):
            tones[s] = r["tone"]

    # rhythm of section backgrounds (never the same tone twice in a row)
    patterns = [
        ["tint", "light", "tint", "dark", "light", "tint"],
        ["light", "tint", "dark", "light", "tint", "light"],
        ["tint", "dark", "light", "tint", "light", "tint"],
        ["light", "dark", "tint", "light", "dark", "light"],
    ]
    pat = rnd.choice(patterns)
    prev = "light" if tones["hero"] == "light" else "dark"
    for i, s in enumerate(sections):
        if s not in tones:
            t = pat[i % len(pat)]
            if t == prev:
                t = "tint" if prev != "tint" else "light"
            tones[s] = t
        prev = tones[s]

    ids = ["font:%s" % font["id"], "radius:%s" % radius["id"], "motif:%d" % MOTIFS.index(motif)]
    ids += ["%s:%s" % (s, rid) for s, rid in recipes.items()]
    return {
        "seed": seed,
        "font": {"id": font["id"], "head": font["head"], "body": font["body"],
                 "url": "https://fonts.googleapis.com/css2?%s&display=swap" % font["q"],
                 "head_stack": "'%s',%s" % (font["head"], font["hs"]),
                 "body_stack": "'%s',%s" % (font["body"], font["bs"])},
        "radius": radius,
        "motif": motif,
        "mood": prof["mood"],
        "svc_label": prof["svc"],
        "cta_label": prof["cta"],
        "recipes": recipes,
        "tones": tones,
        "hero_tone": tones["hero"],
        "ids": ids,
    }


# --------------------------------------------------------------------------- #
# Prompts
# --------------------------------------------------------------------------- #
SYSTEM = """You are a senior web designer and front-end developer at a top agency, building a premium, conversion-focused website for a small business in India. You write ONE section of the page per request.

OUTPUT CONTRACT
- Return ONLY raw HTML for the section: an optional <style> block followed by one <section id="..."> ... </section>. No markdown, no ``` fences, no commentary, no <html>/<head>/<body>, no <script src>, no <link>.
- Scope your CSS: prefix every class you invent with the PREFIX you are given (for example hr-title) so sections never collide. Put layout, hover and responsive rules in ONE <style> block instead of repeating inline styles (keeps the output compact; aim for under ~4000 tokens). Mobile-first, works down to 360px, no horizontal overflow, use clamp(), min() and auto-fit grids.
- Already provided by the page (do NOT redefine): CSS variables --p (primary), --s (secondary), --a (accent), --bg (dark background), --lt (light tint), --td (dark text), --tm (muted text), --gr (brand gradient), --fh (heading font stack), --fb (body font stack), --rc (card radius), --rb (button radius), --ri (image radius); classes .ctr (centred max-width container with side padding), .btn-p (solid primary button), .btn-o (outline button for dark backgrounds), .btn-g (outline button for light backgrounds), .sbadge (small eyebrow badge). AOS is loaded: use data-aos="fade-up" (and data-aos-delay) sparingly. Font Awesome 6 Free is loaded (<i class="fa-solid fa-tooth"></i>, <i class="fa-brands fa-whatsapp"></i>).
- Use var(--fh) for headings and var(--fb) for body text. Take every colour from the variables (rgba()/color-mix() of them is fine); never hard-code another brand colour. Honour --rc / --rb / --ri for corner radius.
- IMAGES: you may ONLY use the placeholders listed under IMAGES, written exactly like {{IMG:key}} inside src="..." or url('...'). Never invent, guess or hotlink any other image URL. A key that is not listed does not exist, so design that part without a photo (icons, gradients, shapes). Always give meaningful alt text; add loading="lazy" except in the hero.
- Page components you can use:
  SLIDER: <div class="wb-slider" data-mode="slide" data-per-view="3" data-autoplay="0" data-gap="20"><div class="wb-viewport"><div class="wb-track"><div class="wb-slide">...</div>...</div></div></div>. Arrows and dots are added automatically. data-mode="fade" stacks all slides in one grid cell and cross-fades them (each slide defines its own height/content). per-view is the desktop value (2 on tablet, 1 on phones automatically). data-autoplay is milliseconds (0 = off).
  TABS: <div class="wb-tabs"><div class="wb-tab-list"><button class="wb-tab active">...</button>...</div><div class="wb-panels"><div class="wb-panel active">...</div>...</div></div> (the n-th button shows the n-th panel).
  LIGHTBOX: add the attribute data-lightbox to any <img> to open it full-screen on click.
- TRUTHFULNESS: use ONLY facts given in FACTS. Never invent years in business, number of clients, awards, certifications, doctor/staff names, prices, offers/discounts, addresses or opening hours. Where a number is not given, write benefit-led copy without numbers. Service descriptions must be accurate and generic (one short sentence), with no medical/legal guarantees and no "100%" or "best in city" claims.
- COPY: natural, specific to the business type and city, confident and warm; English; no lorem ipsum; no "Welcome to our website". Headlines are short and concrete. Use the business name naturally.
- WhatsApp: when a CTA should contact the business, link to the WHATSAPP url from FACTS (target="_blank" rel="noopener"). For a specific service you may append ?text= with a URL-encoded message such as "Hi, I'd like to know more about <service>".
- ACCESSIBILITY: sensible heading order (only the hero has the page's <h1>), text contrast >= 4.5:1, real <a>/<button> elements.
- Do NOT output a navigation bar, footer or contact form; they exist elsewhere on the page."""

SECTION_BRIEFS = {
    "hero": "The hero of the page. Anchor id must be 'home'. It contains the page's only <h1>. Include the primary CTA (WhatsApp) and a secondary 'Our Services' link to #services. The fixed navigation bar overlaps the top ~80px.",
    "services": "The services / offerings section (anchor id 'services'). Build it from the SERVICES list (all of them, up to 8). Write a one-line accurate description per service.",
    "about": "The about section (anchor id 'about'). Tell the business's story using only FACTS (USP text, city, services). Keep claims modest.",
    "process": "A 'how it works / why choose us' section (anchor id 'process'). Steps and benefits must be generic to this business type and consistent with FACTS.",
    "gallery": "The photo gallery (anchor id 'gallery') built ONLY from the gallery images listed under IMAGES.",
    "testimonials": "The reviews section (anchor id 'testimonials'). See REVIEWS for the content rules.",
    "faq": "A FAQ section (anchor id 'faq') with 6 questions typical for this business type. Answers must be generic and must not state specific prices, timings or guarantees; where details are business-specific, tell the visitor to message on WhatsApp to confirm.",
}


def _clip(v, n=400):
    return re.sub(r"\s+", " ", str(v or "")).strip()[:n]


def allowed_keys(images):
    return {str(i.get("key", "")).lower() for i in (images or []) if i.get("key")}


def build_prompt(section, p):
    if section not in RECIPES:
        raise ValueError("Unknown section: %s" % section)
    brief = p.get("brief") or {}
    facts = p.get("facts") or {}
    kind = IMG_KIND.get(section)
    images = [i for i in (p.get("images") or []) if isinstance(i, dict)
              and kind and str(i.get("key", "")).lower().startswith(kind)]
    recipe_id = (brief.get("recipes") or {}).get(section)
    recipe = next((r for r in RECIPES[section] if r["id"] == recipe_id), RECIPES[section][0])
    tone = (brief.get("tones") or {}).get(section) or recipe.get("tone") or "light"
    font = brief.get("font") or {}
    radius = brief.get("radius") or {}

    services = [_clip(s, 80) for s in (facts.get("services") or [])][:8]
    svc_keys = {i["key"] for i in images}
    svc_lines = []
    for n, s in enumerate(services, 1):
        k = "svc%d" % n
        if section == "services":
            svc_lines.append("%d. %s  %s" % (n, s, ("[photo: {{IMG:%s}}]" % k) if k in svc_keys else "[no photo]"))
        else:
            svc_lines.append("%d. %s" % (n, s))

    if images:
        img_lines = "\n".join("- {{IMG:%s}}  =  %s" % (_clip(i["key"], 20), _clip(i.get("label"), 80)) for i in images)
    else:
        img_lines = "(none - no photos exist for this section; use icons, gradients and shapes only)"

    rating = _clip(facts.get("rating"), 10)
    reviews_n = _clip(facts.get("reviews_n"), 10)
    f_lines = [
        "Business name: %s" % _clip(facts.get("name"), 80),
        "Business type: %s" % _clip(facts.get("type"), 80),
        "City / area: %s" % (_clip(facts.get("city"), 120) or "(not given)"),
        "Phone: %s" % (_clip(facts.get("phone"), 40) or "(not given)"),
        "WHATSAPP url: %s" % (_clip(facts.get("wa_link"), 120) or "(not given - use #contact instead)"),
        "USP / extra info from the owner: %s" % (_clip(facts.get("usp"), 400) or "(none)"),
        "Google rating: %s" % (rating or "(not given)"),
        "Google review count: %s" % (reviews_n or "(not given)"),
        "Opening hours: %s" % (_clip(facts.get("hours"), 120) or "(not given - do not mention hours)"),
    ]

    rev_block = ""
    if section == "testimonials":
        revs = [r for r in (facts.get("reviews") or []) if isinstance(r, dict) and r.get("text")][:6]
        if revs:
            lines = ["REVIEWS (real, supplied by the owner - use them VERBATIM, shorten only by cutting whole sentences; keep names as given; stars = 5 unless stated):"]
            for r in revs:
                lines.append('- "%s" - %s' % (_clip(r.get("text"), 320), _clip(r.get("name"), 40) or "Google reviewer"))
            rev_block = "\n".join(lines)
        else:
            rev_block = ("REVIEWS: none supplied. Create exactly 3 clearly-marked SAMPLE cards so the owner can replace them: neutral generic placeholder wording (no claims of specific results), "
                         "name shown as 'Client name', source line 'Sample review'. Every card must carry a small visible tag reading 'Sample - replace with a real review' (data-sample=\"true\"). "
                         "Do not present them as genuine customer feedback."
                         + (" You may show the real Google rating (%s from %s reviews) in the heading area." % (rating, reviews_n) if rating and reviews_n else ""))

    pre = PREFIX[section]
    sid = ID_OF[section]
    avail_label = {
        "hero": "hero photo keys available: " + (", ".join(i["key"] for i in images) or "none"),
    }.get(section, "")

    user = "\n".join(x for x in [
        "SECTION: %s   (anchor id=\"%s\", CSS class PREFIX \"%s-\")" % (section, sid, pre),
        SECTION_BRIEFS[section],
        "",
        "FACTS:", *f_lines,
        "",
        "SERVICES (indexed):" if section in ("hero", "services", "process", "faq", "about") else "",
        ("\n".join(svc_lines) if svc_lines else "(none given - use 6 typical, generic services for this business type)") if section in ("hero", "services", "process", "faq", "about") else "",
        "Suggested heading for the services section: %s" % _clip(brief.get("svc_label"), 40) if section == "services" else "",
        "Suggested primary CTA wording: %s" % _clip(brief.get("cta_label"), 40),
        "",
        rev_block,
        "" if not rev_block else "",
        "ART DIRECTION (shared by the whole page - keep it consistent):",
        "- Mood: %s" % _clip(brief.get("mood"), 200),
        "- Motif / detailing: %s" % _clip(brief.get("motif"), 200),
        "- Heading font: %s, body font: %s (already loaded; use var(--fh)/var(--fb))" % (_clip(font.get("head"), 40), _clip(font.get("body"), 40)),
        "- Corner style: cards %s, buttons %s, images %s (already in --rc/--rb/--ri)" % (radius.get("card", "16px"), radius.get("btn", "999px"), radius.get("img", "16px")),
        "",
        "SECTION BACKGROUND TONE: %s" % TONE_STYLE.get(tone, TONE_STYLE["light"]),
        "",
        "LAYOUT RECIPE (%s): %s" % (recipe["id"], recipe["text"]),
        "",
        "IMAGES:", img_lines,
        avail_label,
        "",
        "Make it feel hand-crafted and premium, not templated: refined spacing rhythm, a clear visual hierarchy, tasteful hover/transition details and a distinctive touch from the motif. Variation seed: %s (use it to vary small details such as shapes, angles and ordering)." % brief.get("seed", 0),
        "Return ONLY the HTML.",
    ] if x is not None)
    return SYSTEM, user, allowed_keys(images)


# --------------------------------------------------------------------------- #
# Output clean-up
# --------------------------------------------------------------------------- #
IMG_TOKEN = re.compile(r"\{\{\s*IMG:([A-Za-z0-9_]+)\s*\}\}")
VOID = {"area", "base", "br", "col", "embed", "hr", "img", "input", "link", "meta", "param", "source", "track", "wbr"}


def close_unclosed(html):
    lt, gt = html.rfind("<"), html.rfind(">")
    if lt > gt:
        html = html[:lt]
    stack = []
    for m in re.finditer(r"<(/?)([a-zA-Z][a-zA-Z0-9-]*)\b[^>]*?(/?)>", html):
        closing, name, selfc = m.group(1), m.group(2).lower(), m.group(3)
        if name in VOID or selfc:
            continue
        if closing:
            if name in stack:
                while stack and stack[-1] != name:
                    stack.pop()
                stack.pop()
        else:
            stack.append(name)
    return html + "".join("</%s>" % t for t in reversed(stack))


def sanitize_html(html, allowed, truncated=False):
    h = (html or "").strip()
    h = re.sub(r"^```[a-zA-Z]*\s*", "", h)
    h = re.sub(r"\s*```\s*$", "", h)
    h = re.sub(r"<!DOCTYPE[^>]*>", "", h, flags=re.I)
    h = re.sub(r"<title\b.*?</title>", "", h, flags=re.I | re.S)
    h = re.sub(r"</?(html|head|body)\b[^>]*>", "", h, flags=re.I)
    h = re.sub(r"<(meta|link)\b[^>]*>", "", h, flags=re.I)
    h = re.sub(r"<script\b[^>]*\bsrc\s*=[^>]*>\s*</script>", "", h, flags=re.I)
    if truncated:
        h = close_unclosed(h)

    def fix_img(m):
        tag = m.group(0)
        s = re.search(r"\bsrc\s*=\s*([\"'])(.*?)\1", tag, flags=re.I | re.S)
        if not s:
            return ""
        t = IMG_TOKEN.fullmatch(s.group(2).strip())
        if t and t.group(1).lower() in allowed:
            return tag
        return ""

    h = re.sub(r"<img\b[^>]*>", fix_img, h, flags=re.I)

    def fix_url(m):
        inner = m.group(2).strip()
        t = IMG_TOKEN.fullmatch(inner)
        if t:
            return m.group(0) if t.group(1).lower() in allowed else "linear-gradient(transparent,transparent)"
        if inner.startswith("data:image/svg+xml") or inner.startswith("#") or inner.startswith("var("):
            return m.group(0)
        return "linear-gradient(transparent,transparent)"

    h = re.sub(r"url\(\s*(['\"]?)(.*?)\1\s*\)", fix_url, h, flags=re.S)
    # placeholders that survived in plain text / unknown attributes are removed
    h = IMG_TOKEN.sub(lambda m: m.group(0) if m.group(1).lower() in allowed else "", h)
    return h.strip()
