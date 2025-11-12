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
    """
    Convert raw degree to zodiac sign and degree within the sign.
    Accepts float or tuple/list (uses first element).
    """
    if isinstance(deg, (list, tuple)):
        deg = deg[0]
    deg = float(deg) % 360.0
    sign_index = int(deg // 30)
    sign_deg = round(deg % 30, 2)
    return SIGNS[sign_index], sign_deg

def get_local_and_ut(date_str, time_str, lat, lon):
    """
    Build localized datetime for the birth moment using historical timezone
    (from timezonefinder + pytz), then convert to UT and UT decimal hours.
    """
    y, m, d = map(int, date_str.split("-"))
    hh, mm = map(int, time_str.split(":"))
    naive = datetime(y, m, d, hh, mm)

    tz_name = tf.timezone_at(lat=lat, lng=lon)
    if not tz_name:
        # Fallback: if unknown tz, assume given time is already UT
        ut_hours = hh + mm / 60.0
        return {
            "tz_name": None,
            "utc_offset_hours": 0.0,
            "local_dt_iso": naive.isoformat(),
            "ut_dt_iso": datetime(y, m, d, hh, mm, tzinfo=pytz.UTC).isoformat(),
            "ut_hours": ut_hours
        }

    tz = pytz.timezone(tz_name)
    # localize with historical rules (DST etc.)
    try:
        local_dt = tz.localize(naive, is_dst=None)
    except Exception:
        local_dt = tz.localize(naive, is_dst=False)

    ut_dt = local_dt.astimezone(pytz.UTC)
    offset = local_dt.utcoffset()
    offset_hours = (offset.total_seconds() / 3600.0) if offset else 0.0
    ut_hours = ut_dt.hour + ut_dt.minute / 60.0 + ut_dt.second / 3600.0

    return {
        "tz_name": tz_name,
        "utc_offset_hours": round(offset_hours, 2),
        "local_dt_iso": local_dt.isoformat(),
        "ut_dt_iso": ut_dt.isoformat(),
        "ut_hours": ut_hours
    }

@app.route("/")
def home():
    return "Chart of Becoming API is running."

@app.route("/natal", methods=["POST"])
def natal():
    data = request.get_json(force=True, silent=True) or {}

    date = data.get("date")   # "YYYY-MM-DD"
    time = data.get("time")   # "HH:MM"
    lat = data.get("lat")     # e.g. "51.5"
    lon = data.get("lon")     # e.g. "31.3"

    # We intentionally IGNORE any provided "timezone" to avoid wrong offsets.
    if not (date and time and lat and lon):
        return jsonify({"error": "Need: date, time, lat, lon"}), 400

    try:
        lat_f = float(lat)
        lon_f = float(lon)

        # Historical timezone + UT conversion
        tzinfo = get_local_and_ut(date, time, lat_f, lon_f)
        ut = tzinfo["ut_hours"]

        y, m, d = map(int, date.split("-"))
        jd_ut = swe.julday(y, m, d, ut)

        # Houses & angles (Placidus, geocentric)
        houses, ascmc = swe.houses(jd_ut, lat_f, lon_f, b"P")
        asc_deg = ascmc[0]
        mc_deg  = ascmc[1]

        asc_sign, asc_sign_deg = deg_to_sign(asc_deg)
        mc_sign,  mc_sign_deg  = deg_to_sign(mc_deg)

        # Planet positions (Sun..Pluto) — tropical
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
            res = swe.calc_ut(jd_ut, pid)  # build can return tuple of varying length
            lon_p = res[0] if isinstance(res, (list, tuple)) else res
            p_sign, p_deg = deg_to_sign(lon_p)
            planets[name] = {"sign": p_sign, "deg": round(p_deg, 2)}

        return jsonify({
            "input_used": {
                "date": date,
                "time_local": time,
                "lat": lat_f,
                "lon": lon_f
            },
            "timezone_used": {
                "tz_name": tzinfo["tz_name"],
                "utc_offset_hours": tzinfo["utc_offset_hours"],
                "local_datetime": tzinfo["local_dt_iso"],
                "ut_datetime": tzinfo["ut_dt_iso"],
                "ut_decimal_hours": round(tzinfo["ut_hours"], 6),
                "jd_ut": jd_ut
            },
            "Ascendant": {"sign": asc_sign, "deg": round(asc_sign_deg, 2)},
            "MC":        {"sign": mc_sign,  "deg": round(mc_sign_deg,  2)},
            "planets": planets
        })

    except Exception as e:
        return jsonify({"error": str(e)}), 500

if __name__ == "__main__":
    swe.set_ephe_path(".")
    import os
    port = int(os.environ.get("PORT", 8000))  # Render binds $PORT
    app.run(host="0.0.0.0", port=port)
