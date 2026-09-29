"""Catskills Hatzoloh GPS locations from chvac.net - for Sullivan address matching.
Source: https://chvac.net/gps-project-map-1.html"""

SULLIVAN_COLONIES = [
    "52-42 Luxury Villas",
    "A Place In The Sun",
    "Achdus Bungalow Colony-Monroe",
    "Aishel Chaya Rachel-Betzalel Museum",
    "Aishel Properties",
    "All Seasons Camp Site",
    "Alpine Acres-South Fallsburg",
    "Alpine Bungalows-Monticello",
    "Amazing Saving",
    "Appels Bungalows",
    "Armon Estates",
    "Aron Village - Paradise Village",
    "Arrowhead Stables",
    "Avery",
    "Avon-Riverside Estates",
    "Avreichim of Ellenville - Shul",
    "Bais Hamedresh Tzemach Dovid - New Square",
    "Barrons-Four Seasons-Shopron Bungalow Colony",
    "Baxter Stadium - Mountaindale",
    "Bayit V'Gan",
    "BBC",
    "Beaver Lake Bungalows",
    "Beaver Lake Estates",
    "Beechwood Cottages",
    "Be'er Miriam-Camp Malchus-Resort At Accord",
    "Beirach Moshe-Satmar-Mount Hope Bungalows",
    "Beis Medrash Torah Vyirah Drabbeinu Yoel-Shul-Bloo",
    "Beis Medresh Heichal Hakodesh-Breslov Shul",
    "Beis Menachem Lubavitch-Tannersville",
    "Beis Yosef Tzvi-Dushinsky Bucherim Camp",
    "Belle Harbor Apartments",
    "Bernatopia-Rachves Drive",
    "Bethel Sunshine Camp",
    "Beverly Gardens Apartments",
    "Beverly Hills Country Club",
    "Binyan Avos-Viznitz-Gibbers",
    "Black Creek Sanctuary",
    "Blue Maple",
    "Blue Sky Manor",
    "Bnos Devorah Raizel",
    "Bobov-Camp Log And Twig-PA",
    "Boro Park-Mazel",
    "Boymelgreen Homes",
    "Breezeway Farm",
    "Breezy Corners",
    "Brentwood",
    "Breslov Cheder-Cong Ahvath Israel-Liberty Shul",
    "Breslov Girls Camp",
    "Breslov-Lefkowitz Summer Houses",
    "Broadway Estates-Dushinsky-Fialkoffs",
    "Brookside Cottages-Glen Wild",
    "Brookside Estates-Section A-Brookside Bungalow Col",
    "Brookside Estates-Section B-Brook Cottages",
    "Brookside Estates-Section C-Emuna Cottages",
    "Brookview Cottages-Old Rt 17-Harris",
    "Buffalo Colony",
    "Burshtein-Ohr Hatorah-Cromwell",
    "Bush Gardens",
    "Cafe Au Main-Kosher Pizza Store-Bloomingburg",
    "Camelot Woods",
    "Cameo Bungalows",
    "Camp Achim",
    "Camp Adas Bnos Vien-Camp Shira",
    "Camp Adas Yereim-Vien",
    "Camp Agudah",
    "Camp Agudah - Barton Road Entrance",
    "Camp Agudah - Entrance 3",
    "Camp Agudah of Toronto",
    "Camp Agudah-Entrance 2",
    "Camp Agudah-Midwest",
    "Camp Ahavas Yisroel-Viznitz",
    "Camp Aliyah-Bnos Naaleh-Lindenmere-Poconos",
    "Camp Anawana",
    "Camp Avrechim",
    "Camp Avrohom Chaim Heller-Camp Shoresh",
    "Camp Bais Yaakov",
    "Camp Bais Yaakov Of The Rockies",
    "Camp Baiseinu-Machaneinu-Jubilee",
    "Camp Belz-Boys",
    "Camp Bilava-Darkei Chaim-Daytop Rehab-Parksville",
    "Camp Binyan David",
    "Camp Birchas Moshe - Gold Mountain - Spring Glen",
    "Camp Birchas Shmayim-Kasho-Meor Hatalmud-Four Seas",
    "Camp Bnei Shimon Yisroel-Shopron",
    "Camp Bnos Belz",
    "Camp Bnos Maarava",
    "Camp Bnos Naaleh-Camp Aliyah-Camp Rayim",
    "Camp Bnos Sanz",
    "Camp Bnos Yakov Pupa",
    "Camp Bnos Yisroel-Viznitz",
    "Camp Bnos-Delivery Entrance",
    "Camp Bnoseinu",
    "Camp Bnos-Main Entrance",
    "Camp Bonim-Ruach Hachaim-Naarim-Poconos",
    "Camp Camp Of Arts-Chaverim-Poconos",
    "Camp Chaverim Of Yachad",
    "Camp Chavivah-Camp Segula",
    "Camp Chavivim - Kenoza Lake - Valley View Hotel",
    "Camp Chaya Sura",
    "Camp Chayil Miriam",
    "Camp Chayolei Hamelech - Machne Menachem",
    "Camp Chayol-Poconos",
    "Camp Chipinew",
    "Camp Condos-Pine Crescent Sanctuary-Nj",
    "Camp CPE-Emunah-Shaloh Torah Cent",
    "Camp David",
    "Camp Dina-Poconos",
    "Camp Dora Golding",
    "Camp Dunn",
    "Camp Emunah-Kids",
    "Camp Emunah-Teen",
    "Camp Engati",
    "Camp Gan Israel-Kiryat Gan Yisroel",
    "Camp Gan Yisroel-Saginaw-Poconos",
    "Camp Gila",
    "Camp Govoah",
    "Camp Hadran Bungalows-Lorraine Bungalows",
    "Camp Hadran-Yeshiva Zichron Meir-Mountaindale Yesh",
    "Camp Hamachane",
    "Camp Hasc",
    "Camp Horim",
    "Camp Horizons",
    "Camp Kamenitz- Kol Aryeh-Degel Hatorah-Jori-Ri",
    "Camp Karlin Stolin",
    "Camp Kasho-Royal Oaks-Swan Lake",
    "Camp Kavunas Halev",
    "Camp Kaylie-Ohel-Camp Summit",
    "Camp Kennybrook",
    "Camp Kindervill-Camp Ger",
    "Camp Kol Yakov Spinka",
    "Camp Krula Boys-Bnos Chedva-Sharei Chedva",
    "Camp Lakota",
    "Camp Lavi",
    "Camp Lehava-Camp Kochavim",
    "Camp Lehava-Tioga-Poconos",
    "Camp Livingston",
    "Camp L'Man Achai",
    "Camp Louemma",
    "Camp Louis",
    "Camp Maaminim - Mogen Avrohom",
    "Camp Machane Yehuda-Hudson Valley Resort-Granite H",
    "Camp Mahanaim",
    "Camp Malka-Kochavim-Ruach Hachaim-Greene County",
    "Camp Mareh Yechezkel-Karlesburg",
    "Camp Mayon HaTorah-Viznitz-Krauts Bungalow",
    "Camp Mechayeh-L'Eila-Poyntelle-Poconos",
    "Camp Merkaaz HaChaim-Brechers-Camp Torah Vodaas-Kingston",
    "Camp Merkaz Hachaim-Chabad Yeshiva Of The Poconos",
    "Camp Mesivta Eitz Chaim-Bobov-Pennsylvania",
    "Camp Mesivta Eitz Chaim-Bobov-Poconos",
    "Camp Mesorah",
    "Camp Migdal",
    "Camp Mizmor",
    "Camp Morasha",
    "Camp Morris - Edison Yeshiva-Zeke-Poconos",
    "Camp Morris-Day Camp-Faculty-Stock",
    "Camp Morris-Kochav",
    "Camp Morris-Merchav Ii",
    "Camp Morris-Merchav-Staff",
    "Camp Morris-Yeshiva",
    "Camp Moshava",
    "Camp Munk",
    "Camp Naaleh-Bobov 45",
    "Camp Nageela Midwest-Camp Red Leaf",
    "Camp Nageela-Jep",
    "Camp Neshama",
    "Camp Nesher",
    "Camp Norr",
    "Camp Novominsk-Poconos",
    "Camp Ohelei Shmuel",
    "Camp Ohr Chedva-Chedva",
    "Camp Ohr Shraga",
    "Camp Ohr Shraga - Staff Cottages",
    "Camp Oorah-The Zone-Boys Campus",
    "Camp Oorah-The Zone-Girls Campus",
    "Camp Oraysa-Aish Mesivta-Camp Darchei Torah",
    "Camp Paye",
    "Camp Pre Mesivta-Camp Kesser",
    "Camp Pupa-Boys",
    "Camp Raninu",
    "Camp Romimu",
    "Camp Ruach Chaim-Cheder-Bei Kyta",
    "Camp Satmar Ky-Round Top",
    "Camp SCHI-Poconos",
    "Camp Seneca Lake-Poconos",
    "Camp Shaarei Yosher",
    "Camp Shabbat",
    "Camp Sharon-Tannersville",
    "Camp Shiloh",
    "Camp Shomria",
    "Camp Shoresh-Wayne-Poconos",
    "Camp Sifsei Dov-Birchwood Estates",
    "Camp Silver Lake-Mesivta D'Masmidim",
    "Camp Silver Lake-Pool-Chaveirim Day Camp",
    "Camp Simcha",
    "Camp Skver-Boys-Glen Wild Road - Bais Yitzchok",
    "Camp Skver-Girls-Glen Wild Road",
    "Camp Skver-Kelly Bridge Road",
    "Camp Spinka-Bais Yitzchok-Milk Rd",
    "Camp Sternberg-Camp Mishkon-Camp Migdal",
    "Camp Tel Yehudah",
    "Camp Teumim - Brookwood",
    "Camp Tiv HaChaim",
    "Camp Tomid-Breslov-Spring Glen",
    "Camp Toras Chaim-Tashbar",
    "Camp Toras Chesed",
    "Camp Tubby",
    "Camp Tzemach Tzedek",
    "Camp Yaldeinu",
    "Camp Yesharim",
    "Camp Yeshiva Of Staten Island",
    "Camp Yeshiva Summer Program-Golden Slipper-Poconos",
    "Camp Yeshiva-Chasan Sofer",
    "Camp Zichron Zvi Dovid-Camp Shalva-Bobov",
    "Candlewood Cottages",
    "Carefree Cottages-Monticello",
    "Carmel Cottages",
    "Carmel Park-Monroe",
    "Carpathian Homes-Kauneonga Lake",
    "Carpathian Paradise-Greenfield Park",
    "Castle Hill Bungalow Colony",
    "Catskills Adventure Resort",
    "Catskills Hatzolah Garage-Brickman Road",
    "Catskills Hatzolah Garage-Swan Lake",
    "Catskills Lake Cabins - Ulster Heights Lake Colony",
    "Catskills Mountains Resort",
    "Center One",
    "Chabad Of Rock Hill",
    "Chai Manor-South Fallsburg",
    "Chai Villas-Swan Lake",
    "Chalet Estates",
    "Chapin Estates",
    "Charlets Apartments",
    "Chestnut Court",
    "Chestnut Ridge Development - Bloomingburg",
    "Chevrah Bikur Cholim Bnai Yisroel",
    "Chuchmas Hatorah-Yeshiva Shar Torah-Kalev-Monticel",
    "Clearview Mountain Country Club-Nof Bahir",
    "Clearwater Estates",
    "Cliff Lodge",
    "Cobbossee-Maine",
    "Cold Spring Garden Apartments",
    "Cold Spring Kottages",
    "Cold Spring Road Bungalows",
    "Concord Golf Club",
    "Concord Hotel",
    "Cong Ohev Shalom-Woodridge Shul",
    "Congregation Anshei Glen Wild",
    "Congregation Anshei Hashoron-Tannersville Shul",
    "Congregation Yetev Lev D'Satmar - Kiryas Yoel -Bais HaMedresh",
    "Continental",
    "Country Cottages",
    "Country Palace",
    "Country Park Cottages",
    "Country Side Way",
    "Country Village-Forestburgh Resort-Town And Countr",
    "Countryside Acres-Loch Sheldrake",
    "Countryside Acres-SIMS-Entrance A-Kiamesha",
    "Countryside Acres-SIMS-Entrance B-Kiamesha",
    "Crescent Hill Synagogue",
    "Crescent Lake Estates",
    "CRMC-Harris Hospital",
    "Cross Road Cottages",
    "Crystal Run Healthcare",
    "Cutlers Cottages",
    "CYM",
    "Darkei Yosher - London Cottages",
    "Davos Pt",
    "Days Inn Liberty",
    "De Hoyos Memorial Park",
    "Deerhill Cottages",
    "Delano Village",
    "Delphic Meadows",
    "Diamond Estates",
    "Dingle Daisy Cottages",
    "Dormo Colony-Shopron",
    "Dr Deutch'S Office",
    "Dr Fleischers Office",
    "Dr Rosen'S Office",
    "Dr Stomans Colony",
    "Dubins",
    "Duso",
    "Dynamite Youth Center",
    "Dynasty Cottages",
    "Echo Mts",
    "Eden Woods",
    "Eilat Cottages",
    "Eisman",
    "Ellenville Citgo",
    "Ellenville Fire-Post Office",
    "Ellenville Library",
    "Ellenville Regional Hospital",
    "Ellenville Shul-Congregation Ezrath Israel",
    "Elm Street Apartments",
    "Elmshade Estates",
    "Emerald Forest Bungalows",
    "Emerald Green Property Owners Association",
    "Emerald Pond Estates",
    "Empire-Malik-Samber Cottages",
    "Evergreen Estates",
    "Excellent Bus Depot",
    "Exxon Gas Station-Monroe",
    "Fallsburg Community Mikvah",
    "Fallsburg Corners",
    "Fallsburg Elementary School",
    "Fallsburg Fire Dept",
    "Fallsburg Fishing Boat Club",
    "Fallsburg Gas",
    "Fallsburg High School",
    "Fallsburg Hills Estate Section-C",
    "Fallsburg Hills Estates-Phyl Bob",
    "Fallsburg Lumber",
    "Fallsburg Police Dept",
    "Fallsburg Post Office",
    "Fallsburg Shul",
    "Fallsview Estates-Old Falls Road Entrance",
    "Fallsview Estates-Riverside Drive Entrance",
    "Fallsview Hotel-Honors Haven Resort",
    "Family Fun Farm",
    "Farsite Bungalows",
    "Five Star Estates",
    "Florida Bungalows",
    "Forest Park Estates",
    "Forestburgh Cottages",
    "Formaggio Estates",
    "Four Star Estates",
    "Franklin Farm",
    "Franklin Farm Camp",
    "Fraser Road Bungalows",
    "Freed'S Colony",
    "Friendship Cottages",
    "Gan Acres",
    "Ganz Bungalow Colony",
    "Garden Cottages - Entrance 1 - Circle 10",
    "Garden Cottages - Entrance 3 - Pool",
    "Garden Hills",
    "Garden Terrace",
    "Garden View Estates",
    "Genes Boats",
    "Geula Estates",
    "Gibbers Lake",
    "Gibbers Red Rocks",
    "Gibbers Watertank",
    "Gitti Gardens",
    "Givat Shalom-Kedem Farms",
    "Glen Wild- Cemetary",
    "Golden Flow",
    "Goldscheins Homestead",
    "Gombo Bakery-Fallsburg",
    "Grand Mountain Resorts",
    "Grand Park Estates",
    "Grandeur Estates-Rachves Estates-Route 42",
    "Grandview Palace-Hotel",
    "Green Acres-Liberty-Pupa",
    "Green Acres-Monticello",
    "Green Hills Estates",
    "Green Lake Estates",
    "Green Pastures",
    "Green Tree Acres",
    "Green Tree Homes",
    "Greene Mountain Inn-Tannersville",
    "Greenfield Meadows-Entrance 2",
    "Greenfield Meadows-Five Star",
    "Greenwalds",
    "Greenwood Park",
    "Gully + Sams Point",
    "Halfway-Monsey-Exit 14B Exxon Station",
    "Halfway-Shortline-Exit 129",
    "Hamaspik Resort-The Lodge-Rock Hill",
    "Hampton Estates",
    "Hanoffee Park",
    "Happy Faces",
    "Happy Hour Stock Farm",
    "Har Nof",
    "Harmony Hills-Laurel Woods",
    "Harris Woods",
    "Hasbrouck Heights Estates",
    "Hebrew Day School Of Sullivan County",
    "Heritage Estates - Jantar",
    "Hershies",
    "Hi Lo",
    "Hidden Ridge",
    "High Ridge Estates-Sunny Day Cottages",
    "High Ridge-Hillside Apts",
    "Highland Park",
    "Hill View Homes - Orchard",
    "Hillcrest Estates",
    "Hilldale Dorms",
    "Hilliar",
    "Hillside Woods-Grand House Bungalows",
    "Himmels Bungalows",
    "Holiday Hills-Monroe",
    "Holiday Mountain Fun Park",
    "Holiday Park-Hajdunanas",
    "Hollywood",
    "Hunter Club",
    "Hurleyville Fire House",
    "Hurleyville Shul",
    "Hyland Resorts",
    "Ichud Hatalmidim D'Satmar- Pine Tree Bungalows-Monticello",
    "Ichud-Satmar-1",
    "Ichud-Satmar-2",
    "Ichud-Satmar-3",
    "Ichud-Satmar-4",
    "Ichud-Satmar-5",
    "Ichud-Satmar-Supermarket",
    "Ilan Hachaim - Breslov - Alberts",
    "Infinity Estates-Parises",
    "Inn By The Falls",
    "Inner Circle",
    "International Riding Camp",
    "Iroquois Springs",
    "Irvington Estates",
    "Jane & Monica",
    "Jans Bungalows",
    "Jened Recreation Village",
    "JF&H",
    "Joyland Acres",
    "K&K",
    "Kaiman Bungalows",
    "KALO - Student Housing - Loch Sheldrake",
    "Kartrite Resort And Waterpark",
    "Kbw Bungalows",
    "Kee Tov Cottages",
    "Kehilas Klausenberg-Camp Shearith Hapleita",
    "Kelder'S Farm",
    "Kfar Chabad - Kingsway",
    "Khal Bais Yitzchok Dspinka-Fleishmanns",
    "Khal Divrei Chaim-Union City",
    "Kiamesha Inn-Kiamesha Owners",
    "Kiamesha Lake Estates",
    "Kiamesha Lanes",
    "Kiamesha Village",
    "Kibbutz Bnai Hayeshivos-Tannserville",
    "Kibbutz Hamesivtos-Yeshiva Ohr Naftoli",
    "Kiryas Avreichim",
    "Kiryas Byrach Moshe-Alladin Hotel",
    "Kiryas Pri Menachem-Beis Medrash Of South Fallsbur",
    "Kiryas Tomishovar",
    "Kiryas Viznitz",
    "Kiryas Yoel Hatzolah Garage-Ky Base",
    "Kiryas Zupnick-Satmar",
    "Klei Kodesh-Satmar-Kutchers Colony",
    "KMS",
    "Knesset Israel - Cemetery",
    "Kol Torah-Bermans",
    "Kollel Damesek Eliezer-Mountain Hill",
    "Kollel of South Fallsburg",
    "Kornfield Cottages",
    "Kosher Mountain-Tannersville",
    "Kozy Acres-Crown Estates-A-Cozy Acres",
    "Kozy Acres-Crown Estates-B-Cozy Acres",
    "Krula Beis Medrash-Bais Yaakov HS of South Fallsburg",
    "Krula Country-Camp Nachlastzvi-Main Entrance-Gambl",
    "Krula Country-Camp Nachlastzvi-Route 42",
    "Kurtz And Lemel",
    "Kutshers Country Club",
    "La Vista Estates-Morningside Cottages-South Fallsb",
    "Lake Forest Estates",
    "Lake Lodge Hotel - Golden Swan",
    "Lakehouse Hotel",
    "Lakehouse Hotel-Delivery Entrance",
    "Lakeshore Hills",
    "Lakeside Villa",
    "Lakeside Villa-Pool",
    "Lakeview Estates-Fallsburg-Route 42",
    "Lakeview Estates-South Fallsburg-Westwood Drive",
    "Lakeview-Loch Sheldrake",
    "Lakewood Cottages",
    "Landaus Supermarket",
    "Landfield Avenue Shul-Cemetery",
    "Lansmans",
    "Lapidus-Grocery-Satmar",
    "Lapidus-Main-Satmar",
    "Lapidus-Schultz Road-Satmar",
    "Laurel Avenue Apartments",
    "Laurel Crest Estates",
    "Laurel Estates",
    "Laurel Ledge Villas",
    "Leisure Lake Estates",
    "Levine Road Colony",
    "Levitz Farms",
    "Lewinters",
    "Liberty Ambulance",
    "Liberty Commons",
    "Liberty Lanes-Liberty Mall",
    "Liberty Police",
    "Liberty Professional Plaza",
    "Liberty Resort",
    "Liberty Road Cottages",
    "Liberty Square Mall",
    "Linmore Estates",
    "Lipkowitz-Back Entrance-Ambulance",
    "Lipkowitz-Main Entrance",
    "Lippman Memorial Park",
    "Living Torah Museum",
    "Loch Sheldrake Shul-Hebrew Congregation",
    "Lou Ann Cottages",
    "Lucky Three Bungalows",
    "Luxor Estates",
    "Luxor Manor",
    "LZ-01-Nevele Grand Hotel",
    "LZ-02-Spring Glen",
    "LZ-03-Kelly'S Field",
    "LZ-04-Hang Glider Road",
    "LZ-05-Caston Road Extension",
    "LZ-06-Edwards Place",
    "LZ-07-7454 Rt 52 West",
    "LZ-08-130 Marcus Road",
    "LZ-09-968 Ulster Heights Road",
    "LZ-10-1099 Ulster Heights Road",
    "LZ-11-Geiger Road",
    "LZ-12-Geiger Road",
    "LZ-13-20 Berme Road",
    "LZ-Apollo",
    "LZ-Charlie Wieners Backyard-Mountain Dale",
    "LZ-Fallsburg Hs",
    "LZ-Krieger Park",
    "LZ-Liberty-Ny State Police",
    "LZ-Monticello Hs",
    "LZ-Rock Hill Fire Department",
    "LZ-Woodbourne Firemans Grounds",
    "M And M-Swiss Hill Cottages",
    "Machne Alexander",
    "Machne Alexsander-Parksville-MaNaVu",
    "Machne Arugos Habosem-Tzelem",
    "Machne Bais Rochel",
    "Machne Be'er Hatorah - Edgewood Bungalows-Sheldrake",
    "Machne Binyan Olam-Tannig-Friends Bungalows",
    "Machne Bnai Yeshua-Neustadt Country-Nadvarna",
    "Machne Bnei Bobov 45-Spinka-Sva Ratzon",
    "Machne Bnos Skver-Camp Shane-Harris Road",
    "Machne Bnos Skver-Kesser",
    "Machne Bnos Square",
    "Machne Chaim V'Shalom-Munkacz",
    "Machne Chevraye",
    "Machne Divrei Yoel-Main Entrance",
    "Machne Divrei Yoel-Rt 55",
    "Machne Eitz Chaim - Sanz - Maple Terrace",
    "Machne Heichal Hatorah",
    "Machne Kalish-Bucherim Camp-Vistula House",
    "Machne Kalish-Bungalows Camp-Vistula House",
    "Machne Kerem Shloma-Bobov-Heiden Rd",
    "Machne Menachem Tzvi - Yeshiva Katana Dsatmar - Yeshivas Chemed",
    "Machne Mevoh Hatalmud",
    "Machne Mishkanos Avrohom Zlatchiv",
    "Machne Nachlas HaTorah D'Krula-Greenfield Park",
    "Machne Nachlas Tzvi Zev",
    "Machne Nusson Tzvi-Boys-Satmar Boys Camp-Kutshers",
    "Machne Nusson Tzvi-Satmar Bucherim Camp-Swan Lake",
    "Machne Ohel Baruch-Krasna",
    "Machne Ohel Fayge-Kollel Country",
    "Machne Ohel Fayge-Lot I-Kollel Country",
    "Machne Ohel Moshe-Krasna",
    "Machne Ohel Yochanon-Rachmastrivka-Yeshiva Pinas Y",
    "Machne Shaar Yisuscher- Dinuv-Fair Oaks",
    "Machne Shulem Moshe-Nitra-Valet Villa Hotel",
    "Machne Stree-Anuvim Estates-Columbia Hill",
    "Machne Toldos Yaakov Yosef-Skver",
    "Machne Tumid",
    "Machne Tumid-Bais Limud Torah-Supreme",
    "Machne Viznitz Bnei Brak-Boys-Sunny Hill",
    "Madison Hill Farm",
    "Mansfield",
    "Maple Shade",
    "Maplewood Estates-Dairyland Road-Woodridge",
    "Maplewood Estates-Maple Avenue-Woodridge",
    "Marigold",
    "Maywood Estates-Thompsonville",
    "Maywood Estates-White Lake",
    "Meadowbrook Gardens-Fantastic Homes",
    "Meadows Estates-Schreibers-Hochmans",
    "Mehadrin Dairy",
    "Mei Menuchos-LaVista Drive-Peaceful Waters",
    "Mei Menuchos-Whittaker Drive-Peaceful Waters",
    "Melody Cottages",
    "Melour Resort-Tannersville",
    "Menorah Bungalow Colony",
    "Menucha Cottages-Adlers-Main Gate",
    "Menucha Cottages-Adlers-Parking Lot",
    "Menucha Motel",
    "Meor Chaim - Eagles Nest",
    "Mesivta Bobov 45-Machne Bnei Bobov 45-Camp Fayge",
    "Mesivta Eitz Chaim",
    "Mesivta Nachlas Yakov - Vien",
    "Mesorah Woods",
    "Miami Beach Cottages",
    "Mike & Nick Blue Sky Inn",
    "Mikvah-Bobov-Monticello",
    "Mikvah-Sanz-White Lake",
    "Millies",
    "Minyan Park Estates",
    "Miron Hill Estates",
    "Mishkanos Bobov-Monticello Resort-Kaufmans",
    "Mishkanos Yoel-Mintz",
    "Mishkanos Yoel-Mintz-Entrance 2",
    "Mobile Medics",
    "Monte Manor",
    "Monticello Beis Medrish",
    "Monticello Fire House",
    "Monticello Raceway",
    "Monticello-Landfield Ave Shul",
    "Moonlight",
    "Morningside Acres-Monticello",
    "Morningside Park Campground",
    "Mosdos Boston-Tannersville",
    "Mount Zion Camp And Retreat C",
    "Mountain Acres - Mountaindale Road",
    "Mountain Acres - New Road",
    "Mountain Crest Bungalows - Fallsburg",
    "Mountain Crest Homes-Mountaindale",
    "Mountain Lake Camps-Wurtsboro",
    "Mountain Lake Cottages-Ulster Heights",
    "Mountain Lake Estates",
    "Mountain Lodge Estates",
    "Mountain View Meadows",
    "Mountain White House",
    "Mountaindale Park",
    "Mountaindale Shul",
    "Mountainwood Acres-Colony Circle-Dr Lockers",
    "Mountainwood Estates",
    "Nachlai Emunah-Aleph",
    "Nachlai Emunah-Bais",
    "Nachlai Emunah-Daled",
    "Nachlai Emunah-Gimmel-Woodland",
    "Nachlas Yaakov-Satmar-Torah Education Center",
    "Naharia-Happy Acres",
    "Naharia-Pool",
    "Naizer Hatorah - Satmar Buchrim Camp - The Glen Wilde",
    "Nappy Lane Mobile Park",
    "Nevele Hotel",
    "Neversink River Hideaway",
    "Neville Estates",
    "New Hope Cottages",
    "Nissenbaum",
    "Nitra - Indian Lake Camp - Burlingham",
    "Noam Eliezer-Skulen-Charm Estates",
    "Nob Hill Country Club",
    "North Wanakasink Club",
    "Novominsk",
    "Nveh Shalom-Koson-Yehivas Nehardue-Mkor Chaim",
    "Oakwood Cottages",
    "ODA Primary Healthcare - Monticello",
    "ODA Primary Healthcare - Woodridge",
    "Ohel Torah - Bergers Yeshiva",
    "Ohr Habahir-Maplewood Gardens-Monticello",
    "Old Falls",
    "Old Liberty Lanes",
    "Old Shul-Tel Yaffa Pool",
    "Olympic Hill",
    "Oppenheimer's Regis Hotel-Main Building-Fleischmann",
    "Oppenheimer's Regis Hotel-Motel Building-Fleischman",
    "Orange Regional Medical Center - Trauma Ii",
    "Orthopedic - Dr Stein",
    "Ou Shaimos-San Giovanni Vizzini",
    "Our Kids Day Camp",
    "Oxford Country Estates",
    "PA Rosenfelds Office",
    "Paradise Bungalow Colony",
    "Paradise Park-Monroe",
    "Paradise Resort",
    "Pardes Paradise",
    "Pardess Chabad Farm",
    "Pardess Colony",
    "Park Cottages - Park View Homes",
    "Park Garden Estates",
    "Park Garden Estates B",
    "Park Side Cottages-Ellenville",
    "Park Side Estates-Monticello",
    "Park Slope Estates",
    "Patio Homes-Anawana Lake Entrance",
    "Patio Homes-Route 42 Entrance",
    "Pelham Parkway Bungalows",
    "Perlers Cottages",
    "Pine Grove Bungalow Colony-Monroe",
    "Pine Grove Cottages-Loch Sheldrake",
    "Pine Hill Estates-DeeLees-Dairyland",
    "Pine Knoll-Monticello",
    "Pine Motel",
    "Pine Oaks - Kol Tuv",
    "Pine Tree Estates-White Lake",
    "Pines Country Estates",
    "Pinewood Estates",
    "Pizza Dpie",
    "Pizzale Pizza",
    "Pleasant Colony",
    "Pleasant Lake Colony",
    "Pleasant Valley Cottages",
    "Pleasant Valley Road Colony - Pleasant Valley Esta",
    "Ponderosa",
    "Post Hill Cottages-Radvan-Edelwise Cottages",
    "Presidential Estates-Main-Rt 55",
    "Presidential Estates-Stanton Road",
    "Quaker Hill Estates (Lower Level)",
    "Quaker Hill Estates (Shul)",
    "Quaker Hill Estates (Upper Level)",
    "Quality Healthcare - Monticello",
    "Quality Healthcare - Swan Lake",
    "Rail Trail - Hurleyville - Main Street",
    "Rail Trail - Liberty - Chestnut Street",
    "Rail Trail - Mountain Dale - Trail A - Greenfield Road",
    "Rail Trail - Mountain Dale - Trail B - Mountain Dale Station",
    "Rail Trail - Parksville - Trail A - Old Route 17",
    "Rail Trail - Parksville - Trail B - Main Street",
    "Rail Trail - Woodridge - Trail A - Tabaczynski Road",
    "Rail Trail - Woodridge - Trail B - Roosevelt Avenue",
    "Rails To Trails",
    "Raleigh Hotel",
    "Refuah Health Center",
    "Regal Wankref Country Colonies",
    "Regency Estates",
    "Relax Inn-Cochecton-Route 52",
    "Relax Inn-Kenoza Lake-Swiss Hill Rd",
    "Renaissance",
    "Reuven Ranch - Sterling Ridge",
    "Rhapsody Fields",
    "Ring Holmstead",
    "River Haven Country Club-Hilltop",
    "River Edge Park",
    "River Manor",
    "River Valley-Entrance 1",
    "River Valley-Entrance 2",
    "River Valley-Entrance 3",
    "Riverside Estates",
    "Riversite-Gamble Road Entrance",
    "Riversite-Rt 42",
    "Robins Woods CoOp",
    "Rock Hill Volunteer Ambulance Corp",
    "Rodef Chesed Workman Circle - Cemetery",
    "Rose Gardens Estates",
    "Rosemond Motel",
    "Rosemond Terrace",
    "Rosenbergs",
    "Rosens",
    "Rosenweig's Colony",
    "Rosetree",
    "Rosewood",
    "Rosmarin Cotages And Day Camp",
    "Royal Brook of Groszvardein",
    "Royal Bungalows-Monticello",
    "RPD Bungalows",
    "Sackett Lake Estates",
    "Sackett Lake Jewish Community Center",
    "Samaritan Rehab",
    "Sams Point- Ice Cave Mountains",
    "Sanz Klausenburg-Mikvah-Divrei Chaim",
    "Satmar - Yeshiva Ktana - Summervile",
    "Satmar Boys Camp-Dairyland-Rav Tov",
    "Satmar Boys Camp-Napanoch",
    "Satmar Girls Camp - Pine Grove Resort Ranch- Kerhonkson",
    "Satmar Girls Camp-Kerhonkson",
    "Satmar Girls Camp-Ulster Heights",
    "Satmar Kollel-Crown Heights Camp-White Lake",
    "Sefarady",
    "Seven Star Estates",
    "Shady Acres",
    "Shady Brook",
    "Shady Pines",
    "Shar Yoshuv",
    "Sheldrake Hills Estates-Sheldrake Dorms",
    "Shermans Service Center",
    "Sheves Achim-Bobov-A",
    "Sheves Achim-Bobov-B",
    "Sheves Achim-Pragers",
    "Shop Rite-Ellenville",
    "Shop Rite-Liberty",
    "Shop Rite-Monticello",
    "Shortline Terminal-Monticello",
    "Shwarma King-Bais Medrash Yakov Aron-Monticello",
    "Silberts Resort",
    "Silver Gate",
    "Silver Pond",
    "Simply Sushi-Monticello",
    "Simply Sweets",
    "Skate Time-Kerhonkson",
    "Skaters World-Ferndale",
    "Skolya Bungalows-Dishners",
    "Skopps",
    "Skyview Bungalows",
    "Skyway Camping Resort",
    "Sloatsburg Rest Stop-Mincha Area",
    "Slovak Country Club",
    "Slovak Sky",
    "South Fallsburg Manor",
    "Speckharts",
    "Spring Glen Corners",
    "Spring Glen Meadows",
    "Spring Glen Synagogue",
    "Spring Lake Retreat",
    "Spring Mountain Resort-Homowack",
    "Springfield",
    "Springwell Manor-Tannersville",
    "Sprinkles Pizza-Four Corners",
    "Spruce Colony",
    "Stage Door",
    "Starlight Marina",
    "Staubers",
    "Sterns",
    "Stewarts-Four Corners",
    "Stolin-Camp Mah-Kee-Nac-Maine",
    "Sugar Hill",
    "Sullivan County Headstart",
    "Summer Hill Country Club",
    "Sun Circle Bungalows",
    "Sun Ranch Bungalows",
    "Sun Ray",
    "Sun Valley",
    "Sunflower Cottages-Petrov",
    "Sunny Forest",
    "Sunny Lake-Karnofsky-White Lake",
    "Sunny Lane-Greenfield Park",
    "Sunrise Bungalows-Rock Hill",
    "Sunrise Park",
    "Sunshine Acres-Lee Shank Lodge-Ellenvile",
    "Sunshine Colony-LaVista Drive",
    "Sunshine Estates-South Fallsburg",
    "Sunshine-Old Liberty Road",
    "Susans",
    "Swan Lake Camp Grounds",
    "Swan Lake Friends-Saltzmans",
    "Swan Lake Pizza",
    "Swan Lake Shul-Teabergs- Ahavas Achim",
    "Swan Lake Villas",
    "Swan Manor-Executive Estates",
    "Swinging Bridge Marina",
    "Tallwood Country Estates",
    "Tamarack Hills",
    "Tamarack Lodge",
    "Tara Acres",
    "Tarre Brae Golf Course",
    "Tarre Brae Village",
    "Tartikov Rt 42-Central Park Estates",
    "Tartikov-Downs Road-Pine Hill Cottages",
    "Tartikov-Fred Road-Park House",
    "Tchernivitz-Happy Hamlet-Green View",
    "Tel Yaffa - Ellenville Retreats",
    "Tel Yaffa 21 - Frog Hollow Road",
    "Temple Lane",
    "The Chalet-Camp Levavi-Camp Machon Lev",
    "The Cottage Club",
    "The Derfl-The Open Well",
    "The Grove Estates",
    "The Inn At Mountain Pines",
    "The Meadows Hotel",
    "The Pines",
    "The Ranch-White Lake",
    "The Willow Pond Resort",
    "The Woods-Davos",
    "Thompsonville Park",
    "Thompsonville-Post Office",
    "Thunder Hill Bungalows",
    "Tikva",
    "Timber Hill",
    "Timberline Camp Ground",
    "Tiny Tots",
    "Town And Country Estates-Loch Sheldrake",
    "Town And Country-Fallsburg",
    "Traveling Tykes",
    "Tree Of Life",
    "Tri Valley Estates",
    "Tribeca Estates",
    "Tristar Village",
    "TRT",
    "Tsanz Krenitz Bungalows",
    "Twin Bridge Estates",
    "Twin Oaks Village",
    "Twin Pines",
    "Ulster Heights Shul-Knesset Yisroel",
    "Ungvar",
    "Urisino",
    "Uzbek",
    "Vacation Village",
    "Venetian Villas",
    "Very Old Hotel Israel",
    "Victoria Colony",
    "Victory Cottages",
    "Villa Agrusa",
    "Villa Roma Hotel Resort",
    "Village Foxcraft",
    "Village Green",
    "Village Park Bungalows",
    "Vitreale Estates",
    "Wagon Wheels",
    "Walmart-Monticello",
    "Walmart-Napanoch",
    "Walnut Mountain Park",
    "Waverly Gardens",
    "Weiners Bungalows",
    "Wellspring",
    "West Park-Palm's Country Club",
    "Westbourne Garden Apts",
    "Westmont-Poconos",
    "Whispering Woods",
    "White House Estates-Hasbrouck Road",
    "White House Estates-Levine Road",
    "White Lake Homes",
    "White Lake Shul-Congregation Beth Sinai",
    "White Lake Villas",
    "White Rock",
    "Willow Acres",
    "Willow Woods",
    "Winaukee-New Hampshire",
    "Windsor Hills Estates",
    "Windy Apts",
    "Woodbourne Correctional Facility",
    "Woodbourne Fire Rec Field",
    "Woodbourne Hills-Woodbourne Estates",
    "Woodbourne Mikva",
    "Woodbourne Shul Cong Bnei Yiroel",
    "Woodlake Village",
    "Woodland Townhouses",
    "Woodlawn Villas",
    "Woodridge Estates",
    "Woodridge Mews Coop",
    "Woodridge Mikva",
    "Woodridge Royal Estates",
    "Woodridge Yeshiva-Yasharesh Yakov",
    "Yagdil Housing",
    "Yaldeinu-Ellenville Pines Colony",
    "Yasgur's Farm",
    "YBM-Golden Hills",
    "Yehiva Ktana-Bobov 45-Ortradnoye",
    "Yellow Shutters",
    "Yeshiva Ahavas HaTorah-Satmar Bucherim-Pine Bush",
    "Yeshiva Birchas Moshe-Noam Elimelech",
    "Yeshiva Darchei Noam",
    "Yeshiva Gedola-Ohel Shloma-Sanz Zvill",
    "Yeshiva Gedola-Satmar-Fleischmanns",
    "Yeshiva Ktana D'Satmar-Budd Road-Nesivos Hatalmud",
    "Yeshiva Ktana D'Satmar-Fred Road-Kerem Shlomo",
    "Yeshiva Ktana D'Satmar-Segar Rosenburg Road-Pleasure Island Resort",
    "Yeshiva Ltziirim Dsatmar-Nesivos Hatalmud",
    "Yeshiva Meor Hatalmud-Machne Kiryas Yoel - Satmar",
    "Yeshiva Meor Hatorah-Shaarei Yosher",
    "Yeshiva Mivtzar Hatorah-Satmar-Machne Keren Hato",
    "Yeshiva Nachlas Tzvi",
    "Yeshiva Ohr Chadash Dprag",
    "Yeshiva Ohr Yeshua Shmuel",
    "Yeshiva Ohr Yisroel",
    "Yeshiva Ohr Yoseph -Neipest",
    "Yeshiva Sanz Klausenberg",
    "Yeshiva Toldos Yakov Yosef - Skver - Monticello",
    "Yeshiva Torah V'Chasidos - Silver Lakes Resort",
    "Yeshiva Toras Chesed",
    "Yeshiva Zichron Moshe-Fallsburg Yeshiva",
    "Yeshivas Hamitzuyoonim-Satmar-Fleischmanns",
    "Yeshivas Kayitz-Camp Shoshanim-Poconos",
    "Yeshivas Mivakshei Torah-Machne Behutz",
    "Yeshivas Nachlas Aharon-Satmar-Daytop-Swan Lake",
    "Yeshivas Ocean-R Yechiel Milller",
    "Yeshivas Viznitz",
    "Yo1 Wellness Resort And Spa Catskills",
    "Yochis-Fallsburg Bagels And Bakery",
    "Yogi Bear Jellystone Park",
    "Zakarin Paper-Fallsburg",
    "Zidichov",
    "Zuckers Glen Wild Hotel",
]

import re
from collections import defaultdict
from dataclasses import dataclass

_SUFFIX_RE = re.compile(
    r"\s+(?:bungalow\s+colony|colony|bungalows|camp\s+site|estates?|camp\s+grounds|grounds)\s*$",
    re.I,
)

# Dispatch shorthand / Whisper variants → canonical CHVAC name (manual overrides auto-aliases).
COLONY_ASR_ALIASES: dict[str, str] = {
    "kutchers": "Klei Kodesh-Satmar-Kutchers Colony",
    "kuchers": "Klei Kodesh-Satmar-Kutchers Colony",
    "klei kodesh": "Klei Kodesh-Satmar-Kutchers Colony",
    "camp agudah": "Camp Agudah",
    "agudah camp": "Camp Agudah",
    "woodbourne hills": "Woodbourne Hills-Woodbourne Estates",
    "woodbourne estates": "Woodbourne Hills-Woodbourne Estates",
    "south fallsburg manor": "South Fallsburg Manor",
    "mount hope": "Beirach Moshe-Satmar-Mount Hope Bungalows",
    "mount hope bungalows": "Beirach Moshe-Satmar-Mount Hope Bungalows",
    "swan lake villas": "Swan Lake Villas",
    "chai villas": "Chai Villas-Swan Lake",
    "alpine acres": "Alpine Acres-South Fallsburg",
    "river edge": "River Edge Park",
    "riveredge": "River Edge Park",
    "river edge trailer park": "River Edge Park",
    "riveredge trailer park": "River Edge Park",
    "sunshine estates": "Sunshine Estates-South Fallsburg",
}
def _normalize_match_text(text: str) -> str:
    t = (text or "").lower()
    t = re.sub(r"[^\w\s\-]", " ", t)
    return re.sub(r"\s+", " ", t).strip()


def _colony_segments(name: str) -> list[str]:
    segs: list[str] = []
    for part in re.split(r"[-–/]", name):
        part = _SUFFIX_RE.sub("", part.strip()).strip()
        if len(part) >= 6:
            segs.append(part)
    return segs


def _build_auto_aliases() -> dict[str, str]:
    """Unique hyphen segments (≥10 chars) → single colony."""
    seg_map: dict[str, set[str]] = defaultdict(set)
    for colony in SULLIVAN_COLONIES:
        for seg in _colony_segments(colony):
            if len(seg) >= 10:
                seg_map[seg.lower()].add(colony)
    return {seg: next(iter(colonies)) for seg, colonies in seg_map.items() if len(colonies) == 1}


_ASR_ALIASES: dict[str, str] = {**_build_auto_aliases(), **COLONY_ASR_ALIASES}

# Verified street addresses for CHVAC colonies (name + address pairs).
# Add rows here or in sullivan_colony_addresses.json — footer only when final
# verified job address matches one of these addresses (not colony name in transcript).
SULLIVAN_COLONY_ADDRESSES: list[dict[str, str]] = [
    {"colony_name": "Klei Kodesh-Satmar-Kutchers Colony", "address": "15 Lake Road"},
    {"colony_name": "River Edge Park", "address": "38 Riveredge Park Trail"},
    {"colony_name": "River Edge Park", "address": "40 Riveredge Trailer Park"},
]

_SUFFIX_COMPARE: dict[str, str] = {
    "st": "street",
    "street": "street",
    "rd": "road",
    "road": "road",
    "ave": "avenue",
    "avenue": "avenue",
    "dr": "drive",
    "drive": "drive",
    "ln": "lane",
    "lane": "lane",
    "blvd": "boulevard",
    "boulevard": "boulevard",
    "pkwy": "parkway",
    "parkway": "parkway",
    "trl": "trail",
    "trail": "trail",
    "ct": "court",
    "court": "court",
    "pl": "place",
    "place": "place",
    "way": "way",
}


@dataclass
class ColonyMatchResult:
    attempted: bool = False
    found: bool = False
    colony_name: str = ""
    colony_address: str = ""
    matched_on: str = ""
    confidence: float = 0.0

    def as_dict(self) -> dict:
        return {
            "attempted": self.attempted,
            "found": self.found,
            "colony_name": self.colony_name,
            "colony_address": self.colony_address,
            "matched_on": self.matched_on,
            "confidence": self.confidence,
        }


def _load_colony_address_entries() -> list[dict[str, str]]:
    entries = list(SULLIVAN_COLONY_ADDRESSES)
    try:
        import json
        from pathlib import Path

        path = Path(__file__).with_name("sullivan_colony_addresses.json")
        if path.is_file():
            data = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(data, list):
                for row in data:
                    if isinstance(row, dict) and row.get("colony_name") and row.get("address"):
                        entries.append(
                            {
                                "colony_name": str(row["colony_name"]).strip(),
                                "address": str(row["address"]).strip(),
                                "street": str(row.get("street", "")).strip(),
                                "city": str(row.get("city", "")).strip(),
                                "state": str(row.get("state", "")).strip(),
                                "source": str(row.get("source", "")).strip(),
                                "lat": row.get("lat"),
                                "lon": row.get("lon"),
                            }
                        )
    except Exception:
        pass
    return entries


_COLONY_ADDRESS_ENTRIES: list[dict[str, str]] = _load_colony_address_entries()


def _normalize_colony_address(addr: str) -> str:
    t = _normalize_match_text(addr)
    t = re.sub(
        r"\b(st|street|rd|road|ave|avenue|dr|drive|ln|lane|blvd|boulevard|pkwy|parkway|trl|trail|ct|court|pl|place|way)\b",
        lambda m: _SUFFIX_COMPARE.get(m.group(1).lower(), m.group(1).lower()),
        t,
    )
    return re.sub(r"\s+", " ", t).strip()


def _parse_house_street(addr: str) -> tuple[str, str, str] | None:
    a = _normalize_colony_address(addr)
    m = re.match(r"^(\d{1,6}(?:-\d{1,6})?)\s+(.+)$", a)
    if not m:
        return None
    house, rest = m.group(1), m.group(2).strip()
    sm = re.search(
        r"\b(street|road|avenue|drive|lane|boulevard|parkway|trail|court|place|way|park)\s*$",
        rest,
    )
    if sm:
        suffix = sm.group(1)
        name = rest[: sm.start()].strip()
    else:
        suffix = ""
        name = rest
    if not name:
        return None
    return house, name, suffix


def _levenshtein(a: str, b: str) -> int:
    if a == b:
        return 0
    if not a:
        return len(b)
    if not b:
        return len(a)
    prev = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        cur = [i]
        for j, cb in enumerate(b, 1):
            cur.append(min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + (ca != cb)))
        prev = cur
    return prev[-1]


def _street_names_match(a: str, b: str) -> bool:
    na = re.sub(r"[^\w\s]", " ", a.lower())
    nb = re.sub(r"[^\w\s]", " ", b.lower())
    na = re.sub(r"\s+", " ", na).strip()
    nb = re.sub(r"\s+", " ", nb).strip()
    if na == nb:
        return True
    return _levenshtein(na, nb) <= 1


def _suffixes_compatible(a: str, b: str) -> bool:
    if not a or not b:
        return True
    return _SUFFIX_COMPARE.get(a.lower(), a.lower()) == _SUFFIX_COMPARE.get(b.lower(), b.lower())


def _addresses_match_for_colony(job_addr: str, colony_addr: str) -> tuple[bool, float]:
    nj = _normalize_colony_address(job_addr)
    nc = _normalize_colony_address(colony_addr)
    if nj and nj == nc:
        return True, 1.0
    jp = _parse_house_street(job_addr)
    cp = _parse_house_street(colony_addr)
    if not jp or not cp:
        return False, 0.0
    if jp[0] != cp[0]:
        return False, 0.0
    if not _street_names_match(jp[1], cp[1]):
        return False, 0.0
    if not _suffixes_compatible(jp[2], cp[2]):
        return False, 0.0
    conf = 1.0 if jp[1] == cp[1] and jp[2] == cp[2] else 0.92
    return True, conf


def match_colony_for_verified_address(verified_address: str) -> ColonyMatchResult:
    """
    Match colony only from the final verified job address against colony address rows.
    Never uses transcript fragments or colony names spoken in audio.
    """
    result = ColonyMatchResult(attempted=bool((verified_address or "").strip()))
    if not result.attempted:
        return result
    parts = [p.strip() for p in (verified_address or "").split(",")]
    job = parts[0]
    job_area = (parts[1] if len(parts) >= 3 else "").lower()
    job_state = (parts[2].strip().split()[0].lower() if len(parts) >= 3 else "")
    candidates: list[ColonyMatchResult] = []
    for row in _COLONY_ADDRESS_ENTRIES:
        colony_name = row["colony_name"]
        colony_addr = row["address"]
        raw = [p.strip() for p in colony_addr.split(",")]
        if job_area and len(raw) >= 2:
            raw_area = re.sub(r"\b[A-Z]{2}\b.*$", "", raw[1], flags=re.I).strip().lower()
            raw_state = str(row.get("state") or "").strip().lower() or (
                re.search(r"\b([A-Z]{2})\b", raw[-1], re.I).group(1).lower()
                if re.search(r"\b([A-Z]{2})\b", raw[-1], re.I) else "")
            if (raw_area and raw_area != job_area) or (job_state and raw_state and raw_state != job_state):
                continue
        ok, conf = _addresses_match_for_colony(job, raw[0])
        if not ok:
            continue
        candidates.append(ColonyMatchResult(
            attempted=True, found=True, colony_name=colony_name,
            colony_address=colony_addr, matched_on=job, confidence=conf))
    # One street number can host several named sites. Address equality alone
    # cannot pick one; leave the footer blank until an exact site is known.
    names = {r.colony_name for r in candidates}
    if len(names) > 1:
        return result
    best = candidates[0] if candidates else None
    if best:
        print(
            f"[COLONY] Matched {best.colony_name!r} — job {best.matched_on!r} "
            f"= colony address {best.colony_address!r} (confidence={best.confidence:.2f})"
        )
        return best
    print(f"[COLONY] No colony address match for verified job location {job!r}")
    return result


def match_sullivan_colony(text: str) -> str | None:
    """Return CHVAC colony name if text contains it (exact, alias, or hyphen segment). Longest wins."""
    if not text:
        return None
    t = _normalize_match_text(text)
    if not t:
        return None

    matches = [c for c in SULLIVAN_COLONIES if c.lower() in t]
    if matches:
        return max(matches, key=len)

    alias_hits: list[str] = []
    for alias, colony in sorted(_ASR_ALIASES.items(), key=lambda x: -len(x[0])):
        if alias in t and colony in SULLIVAN_COLONIES:
            alias_hits.append(colony)
    if alias_hits:
        return max(alias_hits, key=len)

    seg_hits: list[str] = []
    for colony in SULLIVAN_COLONIES:
        for seg in _colony_segments(colony):
            sl = seg.lower()
            if len(sl) >= 8 and sl in t:
                seg_hits.append(colony)
                break
    if seg_hits:
        return max(seg_hits, key=len)
    return None


def unique_named_site_in_transcript(text: str, *, source_profile: str = "") -> dict | None:
    """CHVAC name -> location candidate, never a posting authorization.

    Exact full names only. Colliding names, out-of-Sullivan entries, generic
    fragments and repeated entries are unresolved. Geocode and spoken-area
    checks remain the caller's independent posting gates.
    """
    if source_profile.removeprefix("zello-") != "sullivan":
        return None
    spoken = _normalize_match_text(text)
    if not spoken:
        return None
    candidates: list[dict] = []
    for row in _COLONY_ADDRESS_ENTRIES:
        name = _normalize_match_text(row["colony_name"])
        if len(name) < 10 or not re.search(r"(?<!\w)" + re.escape(name) + r"(?!\w)", spoken):
            continue
        candidates.append(row)
    # If a longer name contains a shorter one, only the maximal literal match
    # is relevant; then apply geographic and address gates. A longer foreign
    # match must never fall back to a shorter in-county match.
    maximal = [r for r in candidates if not any(
        len(_normalize_match_text(o["colony_name"])) > len(_normalize_match_text(r["colony_name"]))
        and _normalize_match_text(r["colony_name"]) in _normalize_match_text(o["colony_name"])
        for o in candidates
    )]
    unique = {(r["colony_name"].lower(), r["address"].lower()): r for r in maximal}
    if len(unique) != 1:
        return None
    match = next(iter(unique.values()))
    # A bare base name cannot select one of several mapped entrances/camps.
    match_name = _normalize_match_text(match["colony_name"])
    if any(_normalize_match_text(r["colony_name"]).startswith(match_name + "-")
           for r in _COLONY_ADDRESS_ENTRIES if r is not match):
        return None
    if not match.get("street") or not match.get("city") or match.get("state", "").upper() != "NY":
        return None
    return match


def resolve_colony_for_alert(
    txt: str = "",
    caption: str | None = None,
    *,
    geocode_hint: str | None = None,
    verified_address: str | None = None,
) -> str | None:
    """
    Colony footer only when final verified address matches a colony address row.
    Transcript, caption, and geocode hint strings are ignored for colony footers.
    """
    _ = txt
    _ = caption
    _ = geocode_hint
    match = match_colony_for_verified_address(verified_address or "")
    return match.colony_name if match.found else None
