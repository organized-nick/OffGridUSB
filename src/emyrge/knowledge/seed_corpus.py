"""Built-in offline survival, medical, and STEM seed corpus for Project eMyrge.

Provides rich fallback passages and interactive Khan Academy practice exercises
so RAG queries and curriculum browsing always return verified grounded answers
even while large ZIM archives are still mounting or on minimal USB builds.
"""

from __future__ import annotations

from typing import Any, Dict, List

DEFAULT_ZIM_ARTICLES: Dict[str, Dict[str, Any]] = {
    "Water_purification": {
        "title": "Water purification",
        "url": "A/Water_purification.html",
        "section": "Emergency disinfection",
        "text": (
            "Emergency water disinfection eliminates waterborne pathogens when municipal treatment fails. "
            "Boiling is the most reliable method: bring water to a rolling boil for 1 minute at sea level "
            "or 3 minutes above 2000 meters elevation. For chemical chlorination using unscented household "
            "liquid bleach (6% sodium hypochlorite), add 2 drops per liter (0.1 mL/L) for clear water, or "
            "4 drops per liter (0.2 mL/L) for cloudy or turbid water. Mix thoroughly and wait 30 minutes "
            "(60 minutes for cold or turbid water). Treated water should have a slight chlorine odor. "
            "For 2% tincture of iodine, add 5 drops per liter of clear water or 10 drops per liter of turbid water. "
            "Solar Water Disinfection (SODIS) requires exposing clear PET plastic bottles to direct sunlight "
            "for 6 hours, or 48 hours under overcast skies."
        ),
    },
    "Oral_rehydration_therapy": {
        "title": "Oral rehydration therapy",
        "url": "A/Oral_rehydration_therapy.html",
        "section": "WHO formulation and dosage",
        "text": (
            "Oral Rehydration Therapy (ORT) prevents fatal hypovolemic shock from acute diarrhea and cholera. "
            "The WHO reduced-osmolarity Oral Rehydration Salts (ORS) protocol prescribes 75 mL per kg of body weight "
            "administered over 4 hours for mild to moderate dehydration, followed by clinical reassessment. "
            "If commercial ORS packets are unavailable, an emergency homemade solution is prepared strictly by "
            "dissolving 6 level teaspoons (25.2 g) of sugar and 0.5 level teaspoon (2.9 g) of table salt in "
            "1 liter of safe disinfected drinking water. Excessive salt risks hypernatremia; measure accurately. "
            "For pediatric fever or pain, weight-based paracetamol is 15 mg/kg every 4 to 6 hours (maximum 1000 mg "
            "single dose, 4000 mg daily), and ibuprofen is 10 mg/kg every 6 to 8 hours (maximum 400 mg single dose)."
        ),
    },
    "Crush_syndrome": {
        "title": "Crush syndrome",
        "url": "A/Crush_syndrome.html",
        "section": "Field fluid resuscitation and hyperkalemia",
        "text": (
            "Crush syndrome (traumatic rhabdomyolysis) occurs when prolonged limb compression (>1-4 hours) releases "
            "myoglobin, potassium, and lactic acid into systemic circulation upon extrication, risking sudden cardiac "
            "arrest from hyperkalemia and acute kidney injury. Start aggressive potassium-free fluid resuscitation "
            "BEFORE releasing compression whenever possible (1000 to 1500 mL/hour isotonic 0.9% saline in adults). "
            "NEVER administer potassium-containing fluids such as Ringer's Lactate or standard potassium-containing ORS. "
            "When IV pumps or IV access are unavailable in austere disaster zones, administer potassium-free alkaline "
            "oral rehydration (1 liter clean water + 1 teaspoon baking soda / sodium bicarbonate + 0.5 teaspoon salt + "
            "2 tablespoons sugar) at 500 to 1000 mL/hour in conscious patients, or via nasogastric / proctoclysis "
            "(rectal Murphy drip at 250-500 mL/hour) to maintain urine output > 200 mL/hour and alkalinize urine."
        ),
    },
    "Hypothermia_and_trauma": {
        "title": "Hypothermia",
        "url": "A/Hypothermia.html",
        "section": "Austere rewarming protocol",
        "text": (
            "Hypothermia is defined as core body temperature below 35.0 C (95.0 F). Remove wet clothing immediately "
            "by cutting garments to minimize movement, as rough handling in severe hypothermia (<28 C) can precipitate "
            "ventricular fibrillation. Insulate from ground conductive loss and apply active external trunk rewarming "
            "(warm packs to axillae, chest, and groin — core before extremities to prevent afterdrop shock). "
            "In conscious patients with intact gag reflex, provide warm sweet non-caffeinated fluids."
        ),
    },
    "Amoxicillin_clinical_guide": {
        "title": "Amoxicillin",
        "url": "A/Amoxicillin.html",
        "section": "Dosage and contraindications",
        "text": (
            "Amoxicillin is a broad-spectrum beta-lactam antibiotic used for bacterial pneumonia, otitis media, "
            "sinusitis, skin infections, and dental abscesses. Standard adult dosing is 500 mg orally every 8 hours "
            "or 875 mg every 12 hours. Standard pediatric dosing is 25 to 45 mg/kg/day divided every 8 to 12 hours, "
            "or high-dose 80 to 90 mg/kg/day divided every 12 hours for resistant community-acquired pneumonia "
            "(capped at adult maximum). Contraindicated in patients with documented penicillin or beta-lactam anaphylaxis."
        ),
    },
    "Photovoltaic_system": {
        "title": "Photovoltaic system",
        "url": "A/Photovoltaic_system.html",
        "section": "Off-grid array and battery sizing",
        "text": (
            "Standalone off-grid solar photovoltaic (PV) sizing follows IEEE 1562 and NEC Article 690 standards. "
            "Battery bank capacity in Ampere-hours (Ah) equals (Daily Watt-Hours * Autonomy Days) divided by "
            "(System Voltage * Depth of Discharge * Inverter Efficiency). LiFePO4 batteries safely support 0.80 DoD, "
            "whereas flooded/AGM lead-acid batteries should be limited to 0.50 DoD. Solar PV array wattage equals "
            "Daily Watt-Hours divided by (Peak Sun Hours * System Derating Factor 0.77). Always connect the battery "
            "bank to the MPPT charge controller FIRST before connecting solar PV panels to avoid controller overvoltage."
        ),
    },
    "Electrical_wiring_and_ohms_law": {
        "title": "Voltage drop",
        "url": "A/Voltage_drop.html",
        "section": "DC conductor sizing",
        "text": (
            "Low-voltage 12V and 24V DC off-grid power systems experience severe resistive losses over long cable runs. "
            "Two-conductor DC voltage drop equals 2 * Length_km * Current_A * Resistance_ohm_per_km. NEC recommends "
            "keeping voltage drop below 3% for critical loads and 5% total. Standard annealed copper resistance is "
            "5.211 ohms/km for 12 AWG, 3.277 ohms/km for 10 AWG, 2.061 ohms/km for 8 AWG, and 1.296 ohms/km for 6 AWG."
        ),
    },
    "Wound_care_and_hemorrhage": {
        "title": "Emergency tourniquet and wound management",
        "url": "A/Wound_management.html",
        "section": "Hemorrhage control",
        "text": (
            "Life-threatening extremity arterial bleeding requires immediate direct pressure or a windlass tourniquet "
            "placed 5 to 7 cm (2-3 inches) proximal to the wound (never directly over a joint). Tighten until distal "
            "pulse disappears and bleeding stops, then record exact application time prominently on the casualty. "
            "Irrigate contaminated wounds using high-pressure potable or boiled cooled water (500-1000 mL) or 0.9% saline."
        ),
    },
}


DEFAULT_KHAN_LESSONS: List[Dict[str, Any]] = [
    {
        "subject": "Electrical Engineering",
        "topic": "DC Circuits & Power",
        "lesson_id": "ee-ohms-law",
        "title": "Ohm's Law & Off-Grid Power Dissipation",
        "content": (
            "Ohm's Law defines the fundamental relationship between Voltage (V in volts), Current (I in amperes), "
            "and Resistance (R in ohms): V = I * R. Electrical power (P in watts) delivered to a load is P = V * I, "
            "or equivalently P = I^2 * R = V^2 / R. In 12V DC solar microgrids, doubling system voltage to 24V halves "
            "the current required for the same wattage, cutting resistive cable heating losses (I^2 * R) by 75%."
        ),
        "prerequisites": ["Basic Algebra"],
        "exercises": [
            {
                "id": "ee-ex-1",
                "question": "A 12V DC medical refrigerator draws 60 Watts continuously. How much current (in Amperes) flows through the fuse?",
                "answer": "5 Amperes",
                "hints": ["Use P = V * I", "Rearrange to I = P / V = 60 / 12"],
                "explanation": "I = P / V = 60 W / 12 V = 5 Amperes. With a 125% NEC continuous duty margin, use a 7.5A or 10A fuse.",
            },
            {
                "id": "ee-ex-2",
                "question": "Calculate the current if a 24V battery bank is connected across an 8 ohm heating element.",
                "answer": "3 Amperes",
                "hints": ["Use V = I * R", "I = 24 / 8"],
                "explanation": "By Ohm's Law, I = V / R = 24 V / 8 ohms = 3 Amperes (dissipating 72 Watts).",
            },
        ],
    },
    {
        "subject": "Chemistry & Sanitation",
        "topic": "Solution Concentration & Chlorination",
        "lesson_id": "chem-ppm-dilution",
        "title": "Parts Per Million (ppm) & Sodium Hypochlorite Dilution",
        "content": (
            "Parts per million (ppm) expresses mass ratio in dilute aqueous solutions: 1 ppm equals 1 mg of solute "
            "per liter (mg/L) of water. Standard household bleach contains 6% sodium hypochlorite (60,000 mg/L). "
            "Using the dilution equation C1 * V1 = C2 * V2, adding 0.1 mL (2 drops) of 6% bleach into 1 liter (1000 mL) "
            "of clear water yields approximately 6 mg/L of sodium hypochlorite (~2-4 ppm free available chlorine), "
            "sufficient to inactivate bacteria and viruses within 30 minutes."
        ),
        "prerequisites": ["Ratios and Proportions"],
        "exercises": [
            {
                "id": "chem-ex-1",
                "question": "Using 6% bleach (2 drops per liter for clear water), how many drops are needed for a 20-liter jerrycan of clear water?",
                "answer": "40 drops",
                "hints": ["Multiply 2 drops/L by 20 liters", "1 drop is approximately 0.05 mL"],
                "explanation": "20 L * 2 drops/L = 40 drops (2.0 mL), followed by 30 minutes of contact time.",
            },
        ],
    },
    {
        "subject": "Biology & Health",
        "topic": "Osmosis & Cellular Hydration",
        "lesson_id": "bio-osmosis-ort",
        "title": "Sodium-Glucose Co-Transport & Osmolarity in Rehydration",
        "content": (
            "Intestinal epithelial cells absorb water passively along osmotic gradients generated by the SGLT1 "
            "(sodium-glucose linked transporter 1) symporter protein. Even when cholera or rotavirus toxins block "
            "standard sodium channels, SGLT1 remains intact and transports 1 glucose molecule alongside 2 sodium ions "
            "into enterocytes, drawing water into the bloodstream. WHO reduced-osmolarity ORS (245 mOsm/L) maintains "
            "an equimolar 1:1 glucose-to-sodium ratio so water flows into tissues rather than drawing fluid into the gut."
        ),
        "prerequisites": ["Cell Membranes"],
        "exercises": [
            {
                "id": "bio-ex-1",
                "question": "According to the WHO 75 mL/kg 4-hour ORS rule, what total volume (in mL) is needed for a 12 kg toddler?",
                "answer": "900 mL",
                "hints": ["Multiply weight in kg by 75 mL/kg", "12 * 75"],
                "explanation": "12 kg * 75 mL/kg = 900 mL administered steadily over 4 hours (225 mL/hour).",
            },
        ],
    },
    {
        "subject": "Physics",
        "topic": "Forces, Energy & Thermodynamics",
        "lesson_id": "phys-newton-1",
        "title": "Newton's Laws, Mechanical Advantage & Thermal Boiling",
        "content": (
            "Newton's First Law states an object remains at rest or uniform velocity unless acted upon by a net external "
            "force. In field rigging, pulley block-and-tackle systems multiply lifting force via mechanical advantage "
            "while conserving work (W = F * d). In thermodynamics, atmospheric pressure drops exponentially with altitude, "
            "lowering the boiling point of water (~93 C at 2000 m), requiring 3 minutes of rolling boil above 2000 meters."
        ),
        "prerequisites": ["Kinematics"],
        "exercises": [
            {
                "id": "phys-ex-1",
                "question": "Using an ideal 4:1 pulley block-and-tackle, how many Newtons of pull force are required to lift a 600 N debris beam?",
                "answer": "150 N",
                "hints": ["Divide load force by mechanical advantage (4)", "600 / 4"],
                "explanation": "F_effort = F_load / MA = 600 N / 4 = 150 N (pulling 4 meters of rope per 1 meter lifted).",
            },
        ],
    },
]
