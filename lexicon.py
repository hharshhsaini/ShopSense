"""Reviewed shopping vocabulary mapped onto actual catalog values.

Every product_type, color, pattern, audience and section named here exists in
data/products.json. Query words map to sets of those values; nothing here adds
product facts.
"""
import re

# Words whose trailing "s" is part of the garment name, or whose singular means
# something else ("short" dress vs "shorts").
KEEP_PLURAL = {
    'shorts', 'tights', 'briefs', 'trunks', 'bottoms', 'pumps', 'slides', 'flats', 'glasses',
    'sunglasses', 'pants', 'jeans', 'leggings', 'trousers', 'joggers', 'chinos', 'dungarees',
    'pyjamas', 'pajamas', 'treggings', 'jeggings', 'culottes', 'knickers', 'sweatpants', 'heels',
    'overalls', 'boxers', 'clamdiggers', 'longjohns', 'earmuffs', 'mittens', 'gloves', 'socks',
    'trainers', 'sneakers', 'loafers', 'espadrilles', 'mules', 'moccasins', 'wellingtons',
    'sandals', 'slippers', 'boots', 'brogues', 'flipflops', 'hipsters', 'braces', 'kids', 'mens',
    'womens', 'boys', 'girls', 'ladies', 'jeggings', 'swimwear', 'dress', 'press', 'canvas',
    'chambray', 'lens', 'plus', 'bus', 'gas', 'cutlass', 'bodies', 'series', 'jersey', 'bias',
}

PHRASES = [
    # Joined before tokenizing so multi-word garment names act as one token.
    # (pattern, replacement, substrings that must occur for the pattern to apply)
    (r't[\s-]?shirts?|tee[\s-]?shirts?|\btees?\b', ' tshirt ', ('shirt', 'tee')),
    (r'\bhi[\s-]?tops?\b|\bhigh[\s-]?tops?\b', ' hitops ', ('top',)),
    (r'\bflip[\s-]?flops?\b', ' flipflops ', ('flop',)),
    (r'\bv[\s-]neck', ' vneck ', ('neck',)),
    (r'\bcrew[\s-]neck', ' crewneck ', ('neck',)),
    (r'\bpolo[\s-]neck', ' poloneck ', ('neck',)),
    (r'\bpull[\s-]?overs?\b', ' pullover ', ('over',)),
    (r'\bco[\s-]?ords?\b', ' coord ', ('ord',)),
    (r'\bone[\s-]piece\b', ' swimsuit ', ('suit', 'costume', 'piece')),
    (r'\bsweat[\s-]?shirts?\b', ' sweatshirt ', ('sweat',)),
    (r'\bsweat[\s-]?pants\b', ' sweatpants ', ('sweat',)),
    (r'\bnight[\s-]?dress(es)?\b|\bnight[\s-]?gowns?\b|\bnighties?\b', ' nightdress ', ('night',)),
    (r'\bpj\'?s\b|\bpajamas?\b|\bpyjama\b', ' pyjamas ', ('pj', 'pajama', 'pyjama')),
    (r'\bhand[\s-]?bags?\b', ' handbag ', ('bag',)),
    (r'\bback[\s-]?packs?\b|\bruck[\s-]?sacks?\b', ' backpack ', ('pack', 'sack')),
    (r'\bear[\s-]?rings?\b', ' earrings ', ('ring',)),
    (r'\bsun[\s-]?glasses\b|\bshades\b', ' sunglasses ', ('glass', 'shades')),
    (r'\bswim[\s-]?suits?\b|\bbathing[\s-]suits?\b|\bswimming[\s-]costumes?\b', ' swimsuit ', ('suit', 'costume', 'piece')),
    (r'\bswim(ming)?[\s-](shorts|trunks)\b|\bboard[\s-]?shorts\b', ' swimshorts ', ('shorts', 'trunks')),
    (r'\bsports?[\s-]bras?\b', ' sportsbra ', ('bra',)),
    (r'\bhigh[\s-]heel(ed|s)?\b|\bstilettos?\b', ' heels ', ('heel', 'stiletto')),
    (r'\bballet[\s-](flats|pumps)\b', ' ballerinas ', ('ballet',)),
    (r'\bwork[\s-]?out\b', ' workout ', ('out',)),
    (r'\bt[\s-]?rex\b', ' trex ', ('rex',)),
    (r'\bblack[\s-]tie\b', ' blacktie ', ('tie',)),
    (r'\bwedding[\s-]guest\b', ' wedding ', ('guest',)),
    (r'\bdate[\s-]night\b', ' date ', ('date',)),
    (r'\bdressing[\s-]gowns?\b|\bbath[\s-]?robes?\b', ' robe ', ('gown', 'robe')),
    (r'\bwaist[\s-]?coats?\b', ' waistcoat ', ('coat',)),
    (r'\brain[\s-]?coats?\b', ' raincoat ', ('coat',)),
    (r'\btrench[\s-]?coats?\b', ' trenchcoat ', ('coat',)),
    (r'\bover[\s-]?coats?\b', ' coat ', ('coat',)),
    (r'\bhair[\s-]?bands?\b|\bhead[\s-]?bands?\b|\balice[\s-]bands?\b', ' hairband ', ('band',)),
    (r'\bhair[\s-](clips?|slides?|grips?)\b', ' hairclip ', ('hair',)),
    (r'\bhair[\s-](ties?|elastics?)\b|\bscrunchies?\b', ' scrunchie ', ('hair', 'scrunch')),
    (r'\bwater[\s-]?bottles?\b', ' waterbottle ', ('bottle',)),
    (r'\b(phone|mobile)[\s-](case|cover)s?\b', ' mobilecase ', ('case', 'cover')),
    (r'\bbucket[\s-]hats?\b', ' buckethat ', ('bucket',)),
    (r'\bbaseball[\s-]caps?\b', ' cap ', ('baseball',)),
    (r'\bcross[\s-]?body\b', ' crossbody ', ('body',)),
    (r'\bpolka[\s-]dots?\b', ' dot ', ('polka',)),
    (r'\boff[\s-]white\b', ' offwhite ', ('white',)),
    (r'\bplus[\s-]size\b', ' plussize ', ('size',)),
    (r'\bnew[\s-]?born\b', ' baby ', ('born',)),
]

# Natural spellings of joined tokens, used for embedding queries.
READABLE = {
    'tshirt': 't-shirt', 'hitops': 'hi-top trainers', 'flipflops': 'flip-flops', 'vneck': 'v-neck',
    'crewneck': 'crew-neck', 'poloneck': 'polo-neck', 'coord': 'co-ord set', 'swimshorts': 'swim shorts',
    'sportsbra': 'sports bra', 'blacktie': 'black tie', 'offwhite': 'off-white', 'plussize': 'plus size',
    'waterbottle': 'water bottle', 'mobilecase': 'phone case', 'buckethat': 'bucket hat', 'hairclip': 'hair clip',
    'crossbody': 'cross-body', 'trex': 't-rex', 'nightdress': 'nightdress', 'workout': 'workout',
}

# Concepts: query words -> (catalog product types, description head nouns, category limit).
# A product matches when its product_type is listed, or its description head noun
# is listed and (when given) its category is allowed.
CONCEPTS = {
    'dress': (['dress', 'dresse', 'gown', 'sundress', 'frock'], {'Dress'}, {'dress', 'gown', 'sundress'}, None),
    'skirt': (['skirt', 'miniskirt'], {'Skirt'}, {'skirt'}, None),
    'jeans': (['jeans', 'denims', 'jegging', 'jeggings'], set(), {'jeans', 'jeggings'}, {'Garment Lower body'}),
    'trousers': (['trousers', 'trouser', 'pants', 'slacks', 'chinos', 'chino', 'culottes'],
                 {'Trousers', 'Outdoor trousers'}, {'trousers', 'pants', 'chinos', 'culottes'}, None),
    'joggers': (['joggers', 'jogger', 'sweatpants', 'trackpants', 'tracksuit'], set(),
                {'joggers', 'sweatpants'}, {'Garment Lower body'}),
    'leggings': (['leggings', 'legging', 'treggings', 'yoga'], {'Leggings/Tights'},
                 {'leggings', 'treggings'}, None),
    'shorts': (['shorts'], {'Shorts'}, {'shorts'}, {'Garment Lower body'}),
    'tshirt': (['tshirt'], {'T-shirt'}, {'tshirt'}, None),
    'top': (['top', 'tops', 'camisole', 'cami'], {'Top', 'Vest top', 'T-shirt', 'Blouse'}, {'top'},
            {'Garment Upper body'}),
    'vest_top': (['tank', 'tanktop', 'singlet'], {'Vest top'}, {'vest'}, {'Garment Upper body'}),
    'vest': (['vest', 'gilet', 'waistcoat'], {'Vest top', 'Outdoor Waistcoat', 'Tailored Waistcoat'},
             {'waistcoat', 'gilet'}, None),
    'blouse': (['blouse'], {'Blouse'}, {'blouse'}, None),
    'shirt': (['shirt', 'buttondown', 'flannel'], {'Shirt'}, {'shirt'}, None),
    'polo': (['polo'], {'Polo shirt'}, set(), None),
    'tunic': (['tunic', 'kurta', 'kurti'], set(), {'tunic'}, None),
    'sweater': (['sweater', 'jumper', 'pullover', 'knitwear', 'sweatshirt', 'turtleneck', 'poloneck'],
                {'Sweater'}, {'jumper', 'sweater', 'sweatshirt'}, None),
    'hoodie': (['hoodie', 'hoody', 'hooded'], {'Hoodie'}, {'hoodie'}, None),
    'cardigan': (['cardigan', 'cardi', 'shrug', 'bolero'], {'Cardigan'}, {'cardigan', 'bolero'}, None),
    'jacket': (['jacket', 'bomber', 'windbreaker', 'parka', 'puffer', 'anorak', 'outerwear', 'windcheater'],
               {'Jacket'}, {'jacket', 'parka', 'windbreaker', 'bomber', 'anorak'}, None),
    'coat': (['coat', 'trenchcoat', 'raincoat', 'peacoat', 'overcoat'], {'Coat'},
             {'coat', 'trenchcoat', 'raincoat'}, None),
    'blazer': (['blazer', 'sportcoat'], {'Blazer'}, {'blazer'}, None),
    'suit': (['suit', 'tuxedo', 'tux'], {'Blazer', 'Tailored Waistcoat'}, {'suit'}, None),
    'jumpsuit': (['jumpsuit', 'playsuit', 'romper', 'overall', 'overalls', 'boilersuit'],
                 {'Jumpsuit/Playsuit'}, {'jumpsuit', 'playsuit'}, None),
    'dungarees': (['dungarees', 'dungaree'], {'Dungarees'}, {'dungarees'}, None),
    'bodysuit': (['bodysuit', 'onesie', 'leotard'], {'Bodysuit'}, {'bodysuit', 'leotard'}, None),
    'set': (['coord', 'outfit set', 'twinset', 'two piece'], {'Garment Set'}, set(), None),
    'swimsuit': (['swimsuit', 'monokini'], {'Swimsuit'}, {'swimsuit'}, None),
    'swimwear': (['swimwear', 'swim', 'swimming', 'beachwear'],
                 {'Swimsuit', 'Bikini top', 'Swimwear bottom', 'Swimwear set', 'Swimwear top'}, set(), None),
    'bikini': (['bikini', 'tankini'], {'Bikini top', 'Swimwear set', 'Swimwear bottom'}, {'bikini'},
               {'Swimwear'}),
    'swimshorts': (['swimshorts'], {'Swimwear bottom'}, {'trunks'}, {'Swimwear'}),
    'sarong': (['sarong', 'kaftan', 'caftan', 'coverup', 'pareo'], {'Sarong'}, {'sarong', 'kaftan'}, None),
    'underwear': (['underwear', 'undies', 'lingerie', 'innerwear'],
                  {'Underwear bottom', 'Bra', 'Underwear body', 'Underwear set', 'Underwear corset',
                   'Underdress', 'Kids Underwear top', 'Long John'}, set(), None),
    'briefs': (['briefs', 'panty', 'panties', 'knickers', 'thong', 'hipsters', 'boxers', 'boxer', 'trunk'],
               {'Underwear bottom'}, {'briefs', 'thong', 'boxer', 'trunks'}, {'Underwear', 'Underwear/nightwear'}),
    'bra': (['bra', 'bralette', 'sportsbra', 'brassiere'], {'Bra'}, {'bra', 'bralette'}, None),
    'socks': (['socks', 'sock'], {'Socks'}, {'socks'}, None),
    'tights': (['tights', 'pantyhose', 'stockings', 'nylons'], {'Underwear Tights', 'Leggings/Tights'},
               {'tights'}, None),
    'pyjamas': (['pyjamas', 'sleepwear', 'nightwear', 'loungewear', 'pyjamas'],
                {'Pyjama set', 'Pyjama bottom', 'Pyjama jumpsuit/playsuit', 'Night gown'}, {'pyjamas'}, None),
    'nightdress': (['nightdress', 'nightshirt', 'negligee'], {'Night gown'}, {'nightdress', 'nightshirt'}, None),
    'robe': (['robe', 'kimono'], {'Robe'}, {'robe', 'kimono'}, None),
    'shoes': (['shoes', 'shoe', 'footwear'], set(), set(), {'Shoes'}),
    'sneakers': (['sneakers', 'sneaker', 'trainers', 'trainer', 'hitops', 'kicks', 'runners'],
                 {'Sneakers'}, {'trainers', 'sneakers', 'hitops'}, None),
    'boots': (['boots', 'boot', 'booties', 'bootie', 'wellies', 'wellingtons', 'chelsea'],
              {'Boots', 'Bootie'}, {'boots', 'wellingtons', 'bootees'}, {'Shoes'}),
    'sandals': (['sandals', 'sandal', 'slides', 'mules', 'espadrilles'],
                {'Sandals', 'Heeled sandals'}, {'sandals', 'slides', 'mules', 'espadrilles'}, {'Shoes'}),
    'heels': (['heels', 'heel', 'pumps', 'stiletto', 'wedges', 'wedge', 'slingbacks'],
              {'Pumps', 'Heeled sandals', 'Heels', 'Wedge'}, {'slingbacks'}, {'Shoes'}),
    'flats': (['ballerinas', 'flats', 'loafers', 'loafer', 'moccasins', 'brogues', 'oxfords'],
              {'Ballerinas', 'Flat shoe', 'Flat shoes', 'Moccasins', 'Other shoe'},
              {'loafers', 'moccasins', 'brogues', 'monkstraps'}, {'Shoes'}),
    'slippers': (['slippers', 'slipper'], {'Slippers'}, {'slippers'}, None),
    'flipflops': (['flipflops'], {'Flip flop'}, {'flipflops'}, None),
    'bag': (['bag', 'bags', 'handbag', 'purse', 'tote', 'clutch', 'shopper', 'satchel', 'crossbody',
             'backpack', 'bumbag', 'fannypack'],
            {'Bag', 'Weekend/Gym bag', 'Tote bag', 'Shoulder bag', 'Cross-body bag', 'Backpack', 'Bumbag'},
            {'bag', 'handbag', 'shopper', 'backpack', 'clutch', 'tote'}, None),
    'wallet': (['wallet', 'cardholder'], {'Wallet'}, {'wallet', 'purse'}, None),
    'jewellery': (['jewellery', 'jewelry', 'jewels', 'bling'],
                  {'Earring', 'Earrings', 'Necklace', 'Bracelet', 'Ring'}, set(), None),
    'earrings': (['earrings', 'studs', 'hoops'], {'Earring', 'Earrings'}, {'earrings'}, None),
    'necklace': (['necklace', 'pendant', 'choker', 'chain'], {'Necklace'}, {'necklace', 'choker'}, None),
    'bracelet': (['bracelet', 'bangle', 'anklet'], {'Bracelet'}, {'bracelet', 'bangle'}, None),
    'ring': (['ring'], {'Ring'}, {'ring'}, {'Accessories'}),
    'watch': (['watch', 'wristwatch'], {'Watch'}, {'watch'}, {'Accessories'}),
    'hat': (['hat', 'hats', 'fedora', 'beret', 'sunhat', 'buckethat'],
            {'Hat/beanie', 'Hat/brim', 'Beanie', 'Felt hat', 'Bucket hat', 'Straw hat'}, {'hat', 'beret'}, None),
    'cap': (['cap', 'snapback'], {'Cap/peaked', 'Cap'}, {'cap'}, {'Accessories'}),
    'beanie': (['beanie', 'toque'], {'Hat/beanie', 'Beanie'}, set(), None),
    'scarf': (['scarf', 'scarves', 'shawl', 'stole', 'snood'], {'Scarf'}, {'scarf', 'snood'}, None),
    'gloves': (['gloves', 'glove', 'mittens', 'mitten'], {'Gloves'}, {'gloves', 'mittens'}, None),
    'belt': (['belt'], {'Belt'}, {'belt'}, {'Accessories'}),
    'sunglasses': (['sunglasses', 'sunnies'], {'Sunglasses'}, {'sunglasses'}, None),
    'tie': (['tie', 'necktie', 'bowtie'], {'Tie'}, {'tie'}, {'Accessories'}),
    'hair': (['hairband', 'hairclip', 'scrunchie', 'barrette', 'hairpin'],
             {'Hair clip', 'Hair string', 'Hair/alice band', 'Hair ties', 'Alice band', 'Hairband', 'Headband'},
             {'hairband', 'scrunchie', 'clips'}, None),
    'umbrella': (['umbrella', 'brolly'], {'Umbrella'}, {'umbrella'}, None),
    'costume': (['costume', 'fancy', 'cosplay'], {'Costumes'}, {'costume'}, None),
    'poncho': (['poncho', 'cape'], set(), {'poncho', 'cape'}, None),
    'waterbottle': (['waterbottle'], {'Waterbottle'}, set(), None),
    'mobilecase': (['mobilecase'], {'Mobile case'}, set(), None),
    'accessories': (['accessories', 'accessory'], set(), set(), {'Accessories'}),
}

# Garments that are part of an outfit with a primary item (used for complement intent).
ACCESSORY_CONCEPTS = {
    'bag', 'wallet', 'jewellery', 'earrings', 'necklace', 'bracelet', 'ring', 'watch', 'hat', 'cap',
    'beanie', 'scarf', 'gloves', 'belt', 'sunglasses', 'tie', 'hair', 'umbrella', 'shoes', 'sneakers',
    'boots', 'sandals', 'heels', 'flats', 'slippers', 'flipflops', 'socks', 'accessories',
}

# Default complements by primary concept when the shopper asks for recommendations
# without naming the accompanying item. Ordered best first.
COMPLEMENTS = {
    'dress': ['bag', 'heels', 'earrings', 'necklace', 'sandals'],
    'skirt': ['top', 'blouse', 'bag', 'heels'],
    'jeans': ['tshirt', 'shirt', 'belt', 'sneakers'],
    'trousers': ['shirt', 'blouse', 'belt', 'flats'],
    'joggers': ['hoodie', 'tshirt', 'sneakers'],
    'leggings': ['sportsbra', 'top', 'sneakers'],
    'shorts': ['tshirt', 'sandals', 'cap'],
    'tshirt': ['jeans', 'shorts', 'sneakers'],
    'top': ['jeans', 'skirt', 'bag', 'earrings'],
    'vest_top': ['shorts', 'jeans', 'sandals'],
    'blouse': ['trousers', 'skirt', 'earrings', 'bag'],
    'shirt': ['trousers', 'jeans', 'tie', 'belt'],
    'polo': ['trousers', 'shorts', 'sneakers'],
    'sweater': ['jeans', 'scarf', 'beanie'],
    'hoodie': ['joggers', 'sneakers', 'cap'],
    'cardigan': ['top', 'jeans', 'scarf'],
    'jacket': ['scarf', 'boots', 'gloves', 'beanie'],
    'coat': ['scarf', 'gloves', 'boots', 'beanie'],
    'blazer': ['shirt', 'trousers', 'tie', 'flats'],
    'suit': ['shirt', 'tie', 'flats', 'belt'],
    'jumpsuit': ['bag', 'heels', 'earrings', 'belt'],
    'swimsuit': ['sunglasses', 'sarong', 'hat', 'flipflops'],
    'swimwear': ['sunglasses', 'sarong', 'hat', 'flipflops'],
    'bikini': ['sunglasses', 'sarong', 'hat', 'flipflops'],
    'swimshorts': ['sunglasses', 'cap', 'flipflops', 'tshirt'],
    'bra': ['briefs'],
    'briefs': ['bra'],
    'pyjamas': ['slippers', 'robe'],
    'nightdress': ['robe', 'slippers'],
    'sneakers': ['socks', 'joggers', 'cap'],
    'boots': ['socks', 'jeans', 'scarf'],
    'heels': ['dress', 'bag', 'earrings'],
    'sandals': ['dress', 'bag', 'sunglasses'],
    'bag': ['wallet', 'sunglasses', 'scarf'],
    'sunglasses': ['hat', 'bag'],
    'scarf': ['gloves', 'beanie', 'coat'],
    'hat': ['scarf', 'sunglasses'],
    'beanie': ['scarf', 'gloves'],
    'earrings': ['necklace', 'bracelet'],
    'necklace': ['earrings', 'bracelet'],
}
# Complement-only concepts not used for primary detection.
EXTRA_COMPLEMENT_CONCEPTS = {'sportsbra': (['sportsbra'], {'Bra'}, {'bra'}, None)}

COLORS = {
    'black': ['Black'], 'white': ['White', 'Off White'], 'offwhite': ['Off White'],
    'cream': ['Off White', 'Light Beige'], 'ivory': ['Off White'],
    'grey': ['Grey', 'Dark Grey', 'Light Grey'], 'gray': ['Grey', 'Dark Grey', 'Light Grey'],
    'charcoal': ['Dark Grey'], 'silver': ['Silver'], 'gold': ['Gold'], 'golden': ['Gold'],
    'blue': ['Blue', 'Dark Blue', 'Light Blue', 'Other Blue'], 'navy': ['Dark Blue'],
    'denim': None, 'indigo': ['Dark Blue'], 'cobalt': ['Blue'],
    'red': ['Red', 'Dark Red', 'Light Red', 'Other Red'], 'burgundy': ['Dark Red'], 'maroon': ['Dark Red'],
    'wine': ['Dark Red'], 'crimson': ['Red', 'Dark Red'], 'scarlet': ['Red'],
    'pink': ['Pink', 'Light Pink', 'Dark Pink', 'Other Pink'], 'blush': ['Light Pink'], 'rose': ['Light Pink', 'Pink'],
    'fuchsia': ['Dark Pink', 'Pink'], 'magenta': ['Dark Pink'],
    'green': ['Green', 'Dark Green', 'Light Green', 'Other Green', 'Greenish Khaki'],
    'olive': ['Greenish Khaki', 'Dark Green'], 'khaki': ['Greenish Khaki'], 'mint': ['Light Green'],
    'sage': ['Light Green', 'Greenish Khaki'], 'emerald': ['Dark Green', 'Green'],
    'beige': ['Beige', 'Light Beige', 'Dark Beige', 'Greyish Beige'], 'nude': ['Light Beige', 'Beige'],
    'tan': ['Dark Beige', 'Beige', 'Yellowish Brown'], 'camel': ['Dark Beige', 'Beige', 'Yellowish Brown'],
    'sand': ['Light Beige', 'Beige'], 'taupe': ['Greyish Beige'],
    'brown': ['Yellowish Brown', 'Dark Beige'], 'chocolate': ['Yellowish Brown'], 'cognac': ['Yellowish Brown'],
    'yellow': ['Yellow', 'Light Yellow', 'Dark Yellow', 'Other Yellow'], 'mustard': ['Dark Yellow', 'Yellow'],
    'orange': ['Orange', 'Light Orange', 'Dark Orange', 'Other Orange'], 'rust': ['Dark Orange'],
    'coral': ['Light Orange', 'Orange'], 'peach': ['Light Orange'], 'apricot': ['Light Orange'],
    'purple': ['Purple', 'Light Purple', 'Dark Purple', 'Other Purple'], 'violet': ['Purple', 'Dark Purple'],
    'lilac': ['Light Purple'], 'lavender': ['Light Purple'], 'plum': ['Dark Purple'], 'mauve': ['Light Purple'],
    'turquoise': ['Turquoise', 'Light Turquoise', 'Dark Turquoise', 'Other Turquoise'],
    'teal': ['Dark Turquoise', 'Turquoise'], 'aqua': ['Light Turquoise', 'Turquoise'],
    'bronze': ['Bronze/Copper'], 'copper': ['Bronze/Copper'], 'transparent': ['Transparent'],
    'clear': ['Transparent'],
}
COLORS = {k: v for k, v in COLORS.items() if v}
# Primary catalog value per color word, ranked above other family members.
COLOR_PRIMARY = {
    'black': 'Black', 'white': 'White', 'grey': 'Grey', 'gray': 'Grey', 'blue': 'Blue', 'red': 'Red',
    'pink': 'Pink', 'green': 'Green', 'beige': 'Beige', 'yellow': 'Yellow', 'orange': 'Orange',
    'purple': 'Purple', 'turquoise': 'Turquoise', 'brown': 'Yellowish Brown',
}
NEUTRAL_COLORS = {'Black', 'White', 'Off White', 'Beige', 'Light Beige', 'Dark Beige', 'Greyish Beige',
                  'Grey', 'Dark Grey', 'Light Grey', 'Gold', 'Silver', 'Dark Blue'}

PATTERNS = {
    'striped': ['Stripe'], 'stripe': ['Stripe'], 'stripes': ['Stripe'], 'stripy': ['Stripe'],
    'dot': ['Dot'], 'dotted': ['Dot'], 'spotted': ['Dot'], 'spotty': ['Dot'],
    'checked': ['Check'], 'check': ['Check'], 'checkered': ['Check'], 'plaid': ['Check'],
    'tartan': ['Check'], 'gingham': ['Check'], 'houndstooth': ['Check'],
    'lace': ['Lace'], 'lacy': ['Lace'], 'sequin': ['Sequin'], 'sequined': ['Sequin'], 'sequinned': ['Sequin'],
    'sparkly': ['Sequin', 'Glittering/Metallic', 'Metallic'], 'glitter': ['Glittering/Metallic', 'Sequin'],
    'glittery': ['Glittering/Metallic', 'Sequin'], 'metallic': ['Metallic', 'Glittering/Metallic'],
    'shiny': ['Metallic', 'Glittering/Metallic', 'Sequin'],
    'embroidered': ['Embroidery'], 'embroidery': ['Embroidery'], 'jacquard': ['Jacquard'],
    'melange': ['Melange'], 'marl': ['Melange'], 'argyle': ['Argyle'], 'mesh': ['Mesh'],
    'colourblock': ['Colour blocking'], 'colorblock': ['Colour blocking'],
    'plain': ['Solid'], 'solid': ['Solid'],
    'printed': ['Front print', 'Placement print', 'All over pattern'],
    'graphic': ['Front print', 'Placement print'], 'patterned': ['All over pattern', 'Other pattern'],
    'floral': None, 'flowery': None, 'leopard': None, 'animal': None, 'camo': None, 'camouflage': None,
    'paisley': None, 'tie-dye': None,
}
# Pattern words without a catalog pattern value; matched in product text instead.
PATTERN_TEXT = {
    'floral': {'floral', 'flower', 'flowers', 'flowered'}, 'flowery': {'floral', 'flower', 'flowers'},
    'leopard': {'leopard'}, 'animal': {'animal', 'leopard', 'zebra', 'snakeskin'},
    'camo': {'camouflage', 'camo'}, 'camouflage': {'camouflage', 'camo'}, 'paisley': {'paisley'},
    'striped': {'striped', 'stripes', 'stripe'}, 'stripe': {'striped', 'stripes'}, 'stripes': {'striped', 'stripes'},
    'stripy': {'striped', 'stripes'}, 'dot': {'dot', 'dots', 'spotted'}, 'dotted': {'dot', 'dots'},
    'spotted': {'spotted', 'dots'}, 'spotty': {'spotted', 'dots'},
    'checked': {'checked', 'check', 'checks'}, 'check': {'checked'}, 'checkered': {'checked'},
    'plaid': {'checked', 'tartan'}, 'tartan': {'tartan', 'checked'}, 'gingham': {'gingham', 'checked'},
    'houndstooth': {'dogtooth', 'houndstooth'}, 'lace': {'lace'}, 'lacy': {'lace'},
    'sequin': {'sequins', 'sequin'}, 'sequined': {'sequins'}, 'sequinned': {'sequins'},
    'sparkly': {'glitter', 'glittery', 'sequins', 'metallic', 'sparkly', 'shimmering'},
    'glitter': {'glitter', 'glittery'}, 'glittery': {'glitter', 'glittery'}, 'metallic': {'metallic'},
    'shiny': {'shiny', 'metallic', 'glossy', 'satin'}, 'embroidered': {'embroidered', 'embroidery'},
    'embroidery': {'embroidered', 'embroidery'}, 'jacquard': {'jacquard'}, 'mesh': {'mesh'},
    'printed': {'print', 'printed'}, 'graphic': {'print', 'motif'}, 'patterned': {'patterned'},
    'tie-dye': {'tie-dye'},
}
PATTERNS = {k: v for k, v in PATTERNS.items()}

MATERIALS = {
    'cotton', 'linen', 'silk', 'wool', 'woollen', 'cashmere', 'leather', 'suede', 'denim', 'velvet',
    'satin', 'corduroy', 'jersey', 'chiffon', 'viscose', 'lyocell', 'fleece', 'fur', 'sherpa', 'knit',
    'knitted', 'mohair', 'alpaca', 'tulle', 'crepe', 'twill', 'canvas', 'polyester', 'nylon', 'mesh',
    'organza', 'pile', 'teddy', 'merino', 'modal', 'chambray', 'poplin', 'seersucker', 'muslin', 'gauze',
    'rib', 'ribbed', 'waffle', 'faux', 'imitation', 'vegan', 'organic', 'recycled', 'down', 'padded',
    'quilted', 'waterproof', 'cork', 'straw', 'rubber', 'metal', 'pearl', 'pearls', 'beaded', 'velour',
}
MATERIAL_TEXT = {
    'leather': {'leather'}, 'woollen': {'wool'}, 'fur': {'fur', 'pile'}, 'knit': {'knit', 'knitted'},
    'knitted': {'knit', 'knitted'}, 'ribbed': {'rib', 'ribbed'}, 'rib': {'rib', 'ribbed'},
    'pearl': {'pearl', 'pearls'}, 'pearls': {'pearl', 'pearls'}, 'teddy': {'teddy', 'pile', 'fleece'},
    'vegan': {'imitation'}, 'faux': {'imitation', 'faux'}, 'velour': {'velour', 'velvet'},
}

# Style and fit words: soft relevance cues matched in text.
STYLE_WORDS = {
    'slim', 'skinny', 'regular', 'relaxed', 'loose', 'oversized', 'fitted', 'straight', 'wide', 'flared',
    'bootcut', 'cropped', 'crop', 'high', 'waisted', 'low', 'long', 'short', 'midi', 'maxi', 'mini',
    'sleeveless', 'strapless', 'backless', 'puff', 'wrap', 'pleated', 'ruffle', 'frill', 'flounce',
    'hooded', 'zip', 'buttoned', 'drawstring', 'vneck', 'crewneck', 'poloneck', 'collar', 'collared',
    'bodycon', 'skater', 'aline', 'shift', 'tiered', 'smocked', 'denim', 'ripped', 'distressed',
    'washed', 'stretch', 'tailored', 'double', 'breasted', 'single', 'cargo', 'utility', 'biker',
    'chunky', 'platform', 'ankle', 'knee', 'calf', 'block', 'pointed', 'square', 'round', 'chelsea',
    'lace-up', 'sporty', 'retro', 'vintage', 'basic', 'classic', 'puffed', 'balloon', 'paperbag',
    'mom', 'boyfriend', 'baggy', 'jogger', 'wireless', 'padded', 'push', 'underwired', 'sleeves',
    'sleeved', 'turtleneck', 'mock', 'cowl', 'halterneck', 'halter', 'off-the-shoulder', 'shoulder',
    'quilted', 'sequined', 'embellished', 'beaded', 'cut', 'slit', 'pockets', 'pocket', 'belted',
    'tie', 'scalloped', 'broderie', 'anglaise', 'heavy', 'thin', 'lightweight', 'warm', 'thick',
    'soft', 'chunky', 'small', 'large', 'big', 'mini', 'statement', 'hoop', 'stud', 'drop', 'pendant',
    'graphic', 'logo', 'slogan', 'print', 'motif', 'animal', 'cat', 'dog', 'unicorn', 'dinosaur',
}

# Occasion and use words: soft priors over catalog product types and sections.
OCCASIONS = {
    'dinner': (['Dress', 'Blouse', 'Top', 'Heeled sandals', 'Pumps', 'Jumpsuit/Playsuit', 'Skirt', 'Blazer'],
               'elegant dress for an evening dinner'),
    'date': (['Dress', 'Top', 'Blouse', 'Heeled sandals', 'Skirt'], 'dress for a date night'),
    'party': (['Dress', 'Top', 'Skirt', 'Heeled sandals', 'Jumpsuit/Playsuit', 'Blazer'],
              'party dress with sequins or glitter'),
    'wedding': (['Dress', 'Blazer', 'Shirt', 'Heeled sandals', 'Pumps', 'Tie', 'Jumpsuit/Playsuit'],
                'smart dress or suit for a wedding guest'),
    'blacktie': (['Dress', 'Blazer', 'Shirt', 'Tie', 'Pumps', 'Heeled sandals'], 'formal evening wear'),
    'formal': (['Blazer', 'Shirt', 'Trousers', 'Dress', 'Tie', 'Pumps', 'Tailored Waistcoat'],
               'formal tailored clothing'),
    'office': (['Blazer', 'Shirt', 'Blouse', 'Trousers', 'Skirt', 'Dress', 'Pumps', 'Flat shoe', 'Cardigan', 'Sweater'],
               'smart office workwear'),
    'work': (['Blazer', 'Shirt', 'Blouse', 'Trousers', 'Skirt', 'Dress', 'Cardigan', 'Sweater'], 'smart workwear'),
    'interview': (['Blazer', 'Shirt', 'Blouse', 'Trousers', 'Tie'], 'smart interview outfit'),
    'business': (['Blazer', 'Shirt', 'Trousers', 'Tie'], 'business tailoring'),
    'beach': (['Swimsuit', 'Bikini top', 'Swimwear bottom', 'Swimwear set', 'Sarong', 'Sunglasses', 'Hat/brim',
               'Flip flop', 'Sandals', 'Shorts', 'Dress', 'Straw hat'], 'beachwear for a sunny beach holiday'),
    'pool': (['Swimsuit', 'Bikini top', 'Swimwear bottom', 'Swimwear set', 'Flip flop', 'Sunglasses'],
             'swimwear for the pool'),
    'vacation': (['Dress', 'Shorts', 'Sandals', 'Sunglasses', 'Hat/brim', 'Swimsuit', 'T-shirt'],
                 'summer holiday clothes'),
    'holiday': (['Dress', 'Shorts', 'Sandals', 'Sunglasses', 'Hat/brim', 'Swimsuit', 'T-shirt'],
                'summer holiday clothes'),
    'summer': (['Dress', 'Shorts', 'T-shirt', 'Vest top', 'Sandals', 'Skirt', 'Sunglasses', 'Hat/brim'],
               'light summer clothing'),
    'winter': (['Coat', 'Jacket', 'Sweater', 'Hat/beanie', 'Scarf', 'Gloves', 'Boots', 'Cardigan'],
               'warm winter clothing'),
    'cold': (['Coat', 'Jacket', 'Sweater', 'Hat/beanie', 'Scarf', 'Gloves', 'Boots'], 'warm clothes for cold weather'),
    'snow': (['Coat', 'Jacket', 'Outdoor overall', 'Gloves', 'Hat/beanie', 'Boots'], 'warm padded snow wear'),
    'ski': (['Jacket', 'Outdoor overall', 'Outdoor trousers', 'Gloves', 'Hat/beanie'], 'padded ski wear'),
    'skiing': (['Jacket', 'Outdoor overall', 'Outdoor trousers', 'Gloves', 'Hat/beanie'], 'padded ski wear'),
    'snowboarding': (['Jacket', 'Outdoor overall', 'Outdoor trousers', 'Gloves', 'Hat/beanie'], 'padded ski wear'),
    'job': (['Blazer', 'Shirt', 'Blouse', 'Trousers', 'Skirt', 'Dress'], 'smart workwear'),
    'nye': (['Dress', 'Top', 'Skirt', 'Heeled sandals', 'Jumpsuit/Playsuit', 'Blazer'], 'party dress with sequins or glitter'),
    'eve': (['Dress', 'Top', 'Skirt', 'Heeled sandals', 'Jumpsuit/Playsuit', 'Blazer'], 'evening party outfit'),
    'evening': (['Dress', 'Top', 'Blouse', 'Skirt', 'Heeled sandals', 'Jumpsuit/Playsuit'], 'evening outfit'),
    'celebration': (['Dress', 'Top', 'Skirt', 'Heeled sandals', 'Jumpsuit/Playsuit', 'Blazer'], 'festive party outfit'),
    'clubbing': (['Dress', 'Top', 'Skirt', 'Heeled sandals', 'Jumpsuit/Playsuit'], 'night out party outfit'),
    'swimming': (['Swimsuit', 'Bikini top', 'Swimwear bottom', 'Swimwear set'], 'swimwear'),
    'newborn': (['Bodysuit', 'Garment Set', 'Pyjama jumpsuit/playsuit', 'Jumpsuit/Playsuit', 'Hat/beanie', 'Sleeping sack', 'Soft Toys', 'Cardigan', 'Trousers', 'Socks'], 'soft baby clothes for a newborn'),
    'rain': (['Jacket', 'Coat', 'Boots', 'Umbrella', 'Outdoor overall'], 'waterproof rain jacket'),
    'rainy': (['Jacket', 'Coat', 'Boots', 'Umbrella'], 'waterproof rain jacket'),
    'autumn': (['Jacket', 'Coat', 'Sweater', 'Cardigan', 'Boots', 'Scarf'], 'autumn layers'),
    'fall': (['Jacket', 'Coat', 'Sweater', 'Cardigan', 'Boots', 'Scarf'], 'autumn layers'),
    'spring': (['Jacket', 'Dress', 'Blouse', 'Cardigan', 'Trousers'], 'light spring clothing'),
    'gym': (['Leggings/Tights', 'Shorts', 'Vest top', 'Bra', 'Top', 'Sneakers', 'T-shirt', 'Hoodie'],
            'sportswear for the gym'),
    'workout': (['Leggings/Tights', 'Shorts', 'Vest top', 'Bra', 'Top', 'Sneakers', 'T-shirt'],
                'sportswear for a workout'),
    'running': (['Leggings/Tights', 'Shorts', 'Top', 'Jacket', 'Sneakers', 'T-shirt'], 'running sportswear'),
    'run': (['Leggings/Tights', 'Shorts', 'Top', 'Jacket', 'Sneakers'], 'running sportswear'),
    'yoga': (['Leggings/Tights', 'Bra', 'Vest top', 'Top'], 'yoga sportswear'),
    'training': (['Leggings/Tights', 'Shorts', 'Top', 'Bra', 'Sneakers'], 'training sportswear'),
    'sports': (['Leggings/Tights', 'Shorts', 'Top', 'Bra', 'Sneakers', 'Jacket'], 'sportswear'),
    'hiking': (['Jacket', 'Outdoor trousers', 'Boots', 'Outdoor Waistcoat', 'Cap/peaked'], 'outdoor hiking clothing'),
    'outdoor': (['Jacket', 'Outdoor trousers', 'Outdoor overall', 'Outdoor Waistcoat'], 'outdoor clothing'),
    'sleep': (['Pyjama set', 'Night gown', 'Pyjama bottom', 'Robe', 'Pyjama jumpsuit/playsuit'], 'nightwear for sleeping'),
    'bedtime': (['Pyjama set', 'Night gown', 'Pyjama bottom', 'Robe'], 'pyjamas'),
    'lounge': (['Hoodie', 'Sweater', 'Trousers', 'Pyjama set', 'T-shirt', 'Robe', 'Slippers'], 'soft loungewear'),
    'lounging': (['Hoodie', 'Sweater', 'Trousers', 'Pyjama set', 'T-shirt', 'Robe', 'Slippers'], 'soft loungewear'),
    'lazy': (['Hoodie', 'Sweater', 'Trousers', 'Pyjama set', 'T-shirt', 'Leggings/Tights', 'Slippers'],
             'comfortable relaxed loungewear like hoodies, sweatshirts and joggers'),
    'sunday': (['Hoodie', 'Sweater', 'Trousers', 'T-shirt'], 'relaxed weekend clothing'),
    'weekend': (['Hoodie', 'Sweater', 'Trousers', 'T-shirt', 'Shorts'], 'relaxed weekend clothing'),
    'comfortable': (['Hoodie', 'Sweater', 'Trousers', 'T-shirt', 'Leggings/Tights', 'Sneakers', 'Slippers',
                     'Ballerinas', 'Flat shoe', 'Sandals', 'Bra', 'Pyjama set'], 'soft comfortable clothing'),
    'comfy': (['Hoodie', 'Sweater', 'Trousers', 'T-shirt', 'Leggings/Tights', 'Sneakers', 'Slippers',
               'Ballerinas', 'Flat shoe', 'Sandals', 'Bra', 'Pyjama set'], 'soft comfortable clothing'),
    'walking': (['Sneakers', 'Flat shoe', 'Ballerinas', 'Sandals', 'Boots'], 'comfortable walking shoes like trainers'),
    'walk': (['Sneakers', 'Flat shoe', 'Ballerinas', 'Sandals', 'Boots'], 'comfortable walking shoes like trainers'),
    'sightseeing': (['Sneakers', 'Flat shoe', 'Sandals', 'Bag', 'T-shirt', 'Shorts'], 'comfortable travel clothes'),
    'commute': (['Jacket', 'Coat', 'Bag', 'Sneakers', 'Trousers'], 'practical commuting clothes'),
    'cozy': (['Sweater', 'Cardigan', 'Hoodie', 'Slippers', 'Pyjama set'], 'cosy soft knitwear'),
    'cosy': (['Sweater', 'Cardigan', 'Hoodie', 'Slippers', 'Pyjama set'], 'cosy soft knitwear'),
    'casual': (['T-shirt', 'Trousers', 'Sweater', 'Hoodie', 'Shirt', 'Shorts', 'Sneakers'], 'casual everyday clothing'),
    'everyday': (['T-shirt', 'Trousers', 'Top', 'Sweater'], 'everyday basics'),
    'festival': (['Shorts', 'Top', 'Vest top', 'Dress', 'Boots', 'Hat/brim', 'Sunglasses'], 'festival outfit'),
    'school': (['Trousers', 'Shirt', 'Sweater', 'Bag', 'Skirt', 'Cardigan'], 'school clothing'),
    'travel': (['Bag', 'Trousers', 'T-shirt', 'Jacket', 'Sneakers'], 'travel essentials'),
    'christmas': (['Sweater', 'Dress', 'Pyjama set', 'Costumes'], 'festive christmas clothing'),
    'halloween': (['Costumes', 'T-shirt', 'Sweater'], 'halloween costume'),
    'maternity': (['Dress', 'Top', 'Trousers', 'Bra'], 'maternity wear'),
    'graduation': (['Dress', 'Blazer', 'Shirt', 'Heeled sandals'], 'smart graduation outfit'),
    'brunch': (['Dress', 'Blouse', 'Top', 'Skirt', 'Sandals'], 'pretty daytime outfit'),
    'cocktail': (['Dress', 'Heeled sandals', 'Top'], 'cocktail dress'),
    'prom': (['Dress', 'Heeled sandals', 'Blazer'], 'prom dress'),
    'gift': ([], 'gift'),
    'present': ([], 'gift'),
    'elegant': (['Dress', 'Blouse', 'Blazer', 'Pumps'], 'elegant clothing'),
    'smart': (['Blazer', 'Shirt', 'Trousers', 'Dress'], 'smart clothing'),
    'warm': (['Coat', 'Jacket', 'Sweater', 'Cardigan', 'Hat/beanie', 'Scarf', 'Gloves'], 'warm clothing'),
    'hot': (['Shorts', 'T-shirt', 'Vest top', 'Dress', 'Sandals'], 'light clothes for hot weather'),
    'outfit': ([], 'outfit'),
}

# Weather, season and mood words refine an occasion; when a concrete use (sleep,
# gym, office...) is also named, only the use restricts product types.
MODIFIER_OCCASIONS = {'walking', 'walk', 'hot', 'cold', 'warm', 'summer', 'winter', 'autumn', 'fall', 'spring', 'comfortable', 'comfy',
                      'cozy', 'cosy', 'casual', 'lazy', 'sunday', 'weekend', 'everyday', 'rain', 'rainy', 'elegant',
                      'smart', 'evening', 'gift', 'present', 'outfit'}

# Shopping-intent filler words that carry no product evidence.
STOPWORDS = set('''
a an the and or of for to in on at by with without from into onto my me i im i'm we you your our us
some any something anything things thing stuff item items piece pieces product products clothes
clothing wear wearing wearable apparel garment garments outfit outfits look looks style styles styled
want wants wanted need needs needing looking look find finding show showing give get buy buying
shop shopping purchase please pls would like love prefer preferably ideally maybe really very
that this these those which who what where when how is are be been being am was were it its it's
can could should will shall do does did just also too only even more most less least much many
under below less than over above more cheaper cheap affordable budget inexpensive pricey price priced
priceless costing cost costs within upto up max maximum min minimum least atleast around about
approximately approx between and to rs inr rupees rupee usd dollars bucks each per both all every
good nice great best perfect new latest trendy stylish cute pretty beautiful lovely cool fashionable
suitable appropriate ideal go goes going pair paired pairing matching match matches complement
complementary coordinating accompany accompanying accessorize along plus as well
for her him them their his hers someone somebody person people
day days night time occasion event events one two three
rated rating ratings star stars review reviews reviewed reviewer
essential essentials keep help recommend suggest suggestion suggestions idea ideas options option kind sort type types
'''.split())

AUDIENCE_WORDS = {
    'women': 'women', 'woman': 'women', 'womens': 'women', 'ladies': 'women', 'lady': 'women',
    'female': 'women', 'females': 'women', 'girlfriend': 'women', 'wife': 'women', 'mom': 'women',
    'mum': 'women', 'mother': 'women', 'sister': 'women', 'feminine': 'women', 'her': 'women',
    'men': 'men', 'man': 'men', 'mens': 'men', 'male': 'men', 'males': 'men', 'gents': 'men',
    'gentlemen': 'men', 'guy': 'men', 'guys': 'men', 'boyfriend': 'men', 'husband': 'men',
    'dad': 'men', 'father': 'men', 'brother': 'men', 'masculine': 'men', 'him': 'men',
    'kids': 'kids', 'kid': 'kids', 'children': 'kids', 'child': 'kids', 'childrens': 'kids',
    'boys': 'boys', 'boy': 'boys', 'son': 'boys', 'nephew': 'boys',
    'girls': 'girls', 'girl': 'girls', 'daughter': 'girls', 'niece': 'girls',
    'baby': 'baby', 'babies': 'baby', 'infant': 'baby', 'newborn': 'baby', 'infants': 'baby', 'toddler': 'baby',
    'toddlers': 'baby',
    'teen': 'teen', 'teens': 'teen', 'teenager': 'teen', 'teenagers': 'teen', 'teenage': 'teen',
    'maternity': 'maternity', 'pregnant': 'maternity', 'pregnancy': 'maternity', 'nursing': 'maternity',
    'plussize': 'plus', 'curvy': 'plus',
}
WOMEN_AUDIENCES = {'Ladieswear', 'Ladies Accessories', 'Lingeries/Tights', 'Divided'}
MEN_AUDIENCES = {'Menswear'}
KIDS_AUDIENCES = {'Children Sizes 92-140', 'Children Sizes 134-170', 'Children Accessories, Swimwear'}
BABY_AUDIENCES = {'Baby Sizes 50-98'}
BOY_SECTIONS = {'Kids Boy', 'Young Boy', 'Boys Underwear & Basics', 'Baby Boy'}
GIRL_SECTIONS = {'Kids Girl', 'Young Girl', 'Girls Underwear & Basics', 'Baby Girl'}
UNISEX_KIDS_SECTIONS = {'Kids Outerwear', 'Kids & Baby Shoes', 'Kids Accessories, Swimwear & D', 'Kids Sports',
                        'Kids Local Relevance', 'Baby Essentials & Complements'}

# Popular brands that the frozen catalog does not carry; requests for them are
# unsatisfiable unless the brand word actually occurs in catalog text.
FOREIGN_BRANDS = {
    'adidas', 'nike', 'puma', 'reebok', 'gucci', 'prada', 'chanel', 'dior', 'versace', 'armani', 'zara',
    'uniqlo', 'levis', "levi's", 'levi', 'balenciaga', 'hermes', 'burberry', 'fendi', 'valentino', 'lululemon',
    'converse', 'vans', 'skechers', 'crocs', 'birkenstock', 'timberland', 'rolex', 'casio', 'fossil',
    'rayban', 'ray-ban', 'oakley', 'tommy', 'hilfiger', 'lacoste', 'calvin', 'klein', 'gap', 'mango',
    'shein', 'asos', 'primark', 'supreme', 'yeezy', 'jordan', 'jordans', 'asics', 'fila', 'newbalance',
    'louis', 'vuitton', 'coach', 'kors', 'apple', 'samsung', 'sony', 'xiaomi', 'boss', 'diesel',
    'superdry', 'patagonia', 'columbia', 'northface', 'decathlon', 'biba', 'fabindia', 'manyavar',
}

# Requests that are not shopping for catalog goods.
OFF_TOPIC = {
    'recipe', 'recipes', 'poem', 'essay', 'weather', 'forecast', 'homework', 'translate', 'stock',
    'stocks', 'bitcoin', 'crypto', 'flight', 'flights', 'hotel', 'hotels', 'restaurant', 'pizza',
    'burger', 'groceries', 'grocery', 'vegetables', 'fruit', 'medicine', 'doctor', 'insurance', 'loan',
    'mortgage', 'car', 'cars', 'tyre', 'tyres', 'tire', 'tires', 'engine', 'motorcycle', 'bicycle',
    'laptop', 'laptops', 'computer', 'computers', 'smartphone', 'television', 'tv', 'fridge',
    'refrigerator', 'microwave', 'oven', 'sofa', 'couch', 'mattress', 'bed', 'furniture', 'lamp',
    'printer', 'keyboard', 'mouse', 'monitor', 'headphones', 'earbuds', 'speaker', 'camera', 'drone',
    'console', 'playstation', 'xbox', 'nintendo', 'videogame', 'novel', 'textbook', 'book', 'books',
    'spaceship', 'rocket', 'satellite', 'telescope', 'microscope', 'hammer', 'drill', 'screwdriver',
    'paint', 'cement', 'fertilizer', 'seeds', 'plant', 'plants', 'puppy', 'kitten', 'dogfood',
    'catfood', 'aquarium', 'vitamins', 'protein', 'supplement', 'supplements', 'toothpaste',
    'diamond', 'diamonds', 'ticket', 'tickets', 'concert',
    'movie', 'movies', 'song', 'songs', 'lyrics', 'code', 'python', 'javascript', 'sql', 'program',
    'algorithm', 'math', 'equation', 'tutorial', 'news', 'election', 'president', 'capital',
    'appliance', 'appliances', 'tractor', 'helmet', 'tent', 'generator', 'battery',
    'batteries', 'charger', 'cable', 'router', 'wifi', 'iphone', 'android', 'tablet', 'ipad',
}
# Garments the catalog does not carry at all.
UNAVAILABLE = {'saree', 'sari', 'lehenga', 'sherwani', 'dhoti', 'salwar', 'dupatta', 'abaya', 'burqa',
               'hijab', 'hanbok', 'qipao', 'kilt', 'tutu', 'wetsuit', 'spacesuit', 'armor',
               'armour', 'diaper', 'diapers', 'nappy', 'nappies'}
# Off-topic words that can legitimately describe garments (prints, uses) and only
# count as off-topic when no garment concept is present.
SOFT_OFF_TOPIC = {'python', 'car', 'cars', 'book', 'books', 'movie', 'song', 'plant', 'plants',
                  'paint', 'camera', 'rocket', 'diamond', 'diamonds', 'mouse', 'tent', 'helmet', 'code'}

NEGATIONS = {'not', 'no', 'without', 'except', 'excluding', 'exclude', 'avoid', 'non', 'never', 'nothing',
             'but', 'dont', "don't", 'hate', 'dislike', 'skip', 'minus'}

COMPLEMENT_MARKERS = re.compile(
    r'\b(?:with|and|plus|\+|&)\s+(?:an?\s+|some\s+|the\s+)?(?:matching|coordinating|complementary|'
    r'complementing|co-ordinating|accompanying|suitable|nice|cute)\b'
    r'|\b(?:to\s+(?:go|wear|pair)\s+with|that\s+goes?\s+with|to\s+match|which\s+goes?\s+with|'
    r'paired\s+with|pair\s+(?:it|them)\s+with|to\s+complement|to\s+accessori[sz]e|'
    r'accessori[sz]ed\s+with|complete\s+the\s+look\s+with|complemented\s+by|along\s+with)\b')
