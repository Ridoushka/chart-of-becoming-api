from flask import Flask, request, jsonify
import swisseph as swe
from timezonefinder import TimezoneFinder
import pytz
from datetime import datetime

app = Flask(__name__)
tf = TimezoneFinder()

SIGNS = [
    "Aries", "Taurus", "Gemini", "Cancer",
    "Leo", "Virgo", "Libra", "Scorpio",
    "Sagittarius", "Capricorn", "Aquarius", "Pisces"
]

def deg_to_sign(deg):
    deg = deg % 360.0
    sign_index = int(deg // 30)
    sign_deg = round(deg % 30, 2)
    return SIGNS[sign_index], sign_deg

def get_ut_hours(date_str, time_str, lat, lon, tz_str=None):
    """
    Convert local birth time to UT hours.
    1) If tz_str provided: use it.
    2) Else: detect timezone from lat/lon and date via timezonefinder + pytz.
    """
    hour_str, minute_str = time_str.split(":")
    h = int(hour_str)
    m = int(minute_str)

    # If explicit timezone given -> trust it
    if tz_str:
        sign = 1 if tz_str.startswith("+") else -1
        off_h, off_m = tz_str[1:].split(":")
        offset_hours = sign * (int(off_h) + int(off_m) / 60.0)
        return (h + m / 60.0) - offset_hours

    # Auto-detect timezone
    year, month, day = map(int, date_str.split("-"))
    local_naive = datetime(year, month, day, h, m)

    tz_name = tf.timezone_at(lat=lat, lng=lon)
    if not tz_name:
        # If unknown: assume input already UT
        return h + m / 60.0

    tz = pytz.timezone(tz_name)
    try:
        local_dt = tz.localize(local_naive, is_dst=None)
    except Exception:
        local_dt = tz.localize(local_naive, is_dst=False)

    ut_dt = local_dt.astimezone(pytz.UTC)
    return ut_dt.hour + ut_dt.minute / 60.0 + ut_dt.second / 3600.0

@app.route("/")
def home():
    return "Chart of Becoming API is running."

@app.route("/natal", methods=["POST"])
def natal():
    data = request.get_json()

    date = data.get("date")       # "YYYY-MM-DD"
    time = data.get("time")       # "HH:MM"
    lat = data.get("lat")         # "51.5"
    lon = data.get("lon")         # "31.3"
    tz = data.get("timezone")     # optional

    if not (date and time and lat and lon):
        return jsonify({
            "error": "Missing required fields. Need: date, time, lat, lon. Timezone optional."
        }), 400

    try:
        lat_f = float(lat)
        lon_f = float(lon)

        ut = get_ut_hours(date, time, lat_f, lon_f, tz)

        year, month, day = map(int, date.split("-"))
        jd_ut = swe.julday(year, month, day, ut)

        # Houses & angles (Placidus)
        houses, ascmc = swe.houses(jd_ut, lat_f, lon_f, b"P")
        asc_deg = ascmc[0]
        mc_deg = ascmc[1]

        asc_sign, asc_sign_deg = deg_to_sign(asc_deg)
        mc_sign, mc_sign_deg = deg_to_sign(mc_deg)

        # Planets Sun..Pluto
        planet_ids = {
            "Sun": swe.SUN,
            "Moon": swe.MOON,
            "Mercury": swe.MERCURY,
            "Venus": swe.VENUS,
            "Mars": swe.MARS,
            "Jupiter": swe.JUPITER,
            "Saturn": swe.SATURN,
            "Uranus": swe.URANUS,
            "Neptune": swe.NEPTUNE,
            "Pluto": swe.PLUTO
        }

        planets = {}
        for name, pid in planet_ids.items():
            lon_p, _, _ = swe.calc_ut(jd_ut, pid)
            p_sign, p_deg = deg_to_sign(lon_p)
            planets[name] = {
                "sign": p_sign,
                "deg": round(p_deg, 2)
            }

        return jsonify({
            "Ascendant": {"sign": asc_sign, "deg": round(asc_sign_deg, 2)},
            "MC": {"sign": mc_sign, "deg": round(mc_sign_deg, 2)},
            "planets": planets
        })

    except Exception as e:
        return jsonify({"error": str(e)}), 500

if __name__ == "__main__":
    swe.set_ephe_path(".")
    app.run(host="0.0.0.0", port=8000)

