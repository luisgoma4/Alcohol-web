"""Standard values for the BrAC calculator: the single source of truth for
defaults, the drinks behind the quick-add buttons, meal options and limits."""

# Profile and basic inputs
DEFAULTS = {
    "lang": "es",
    "sex": "male",
    "age_years": 35,
    "weight_kg": 70,
    "height_cm": 175,
    "food": "light",
    "limit_profile": "general",
    "limit_brac": 0.25,
    "limit_bac": 0.50,
}

# Advanced model parameters (hidden at the bottom of the page)
ADVANCED_DEFAULTS = {
    "habitual_level": 0.5,
    "breath_temp_c": 34.0,
    "vd_method": "watson",
    "r_widmark": 0.60,
    "ka_h": 2.4,
    "carbonation_factor": 1.1,
    "elimination_mode": "mm",
    "Vmax_g_per_L_h": 0.20,
    "Km_g_per_L": 0.15,
    "beta_g_per_L_h": 0.18,
    "ke_h": 0.15,
    "BBR_base": 2100.0,
    "bbr_temp_coeff_per_deg": 0.0,
    "dt_h": 0.0025,
}

# Drinks for the quick-add buttons and the "Drink" column.
# ml = volume of the alcoholic part; abv = fraction (0-1);
# carbonated drinks are absorbed somewhat faster.
DRINKS = {
    "cana":    {"emoji": "🍺", "ml": 200, "abv": 0.05, "carbonated": True},
    "tercio":  {"emoji": "🍺", "ml": 330, "abv": 0.05, "carbonated": True},
    "pinta":   {"emoji": "🍺", "ml": 500, "abv": 0.05, "carbonated": True},
    "vino":    {"emoji": "🍷", "ml": 150, "abv": 0.12, "carbonated": False},
    "cava":    {"emoji": "🥂", "ml": 120, "abv": 0.115, "carbonated": True},
    "chupito": {"emoji": "🥃", "ml": 40,  "abv": 0.30, "carbonated": False},
    "copa":    {"emoji": "🍸", "ml": 50,  "abv": 0.40, "carbonated": True},
}

# Which drinks get a quick-add button (in order)
QUICK_DRINKS = ["cana", "tercio", "vino", "copa", "chupito"]

# Meal -> absorption factor (food slows absorption)
FOOD_FACTORS = {"fasting": 1.0, "light": 0.8, "heavy": 0.6}

# Legal limit profiles (Spain): BrAC mg/L air, BAC g/L blood
LIMITS = {
    "general": (0.25, 0.50),
    "novice": (0.15, 0.30),
}

STORAGE_KEY = "brac_profile_v1"
