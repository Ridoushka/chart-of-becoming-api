# main.py
from flask import Flask, request, jsonify
import swisseph as swe
from timezonefinder import TimezoneFinder
import pytz
from datetime import datetime
import os

app = Flask(__name__)
tf = TimezoneFinder()

# Toggle to enable/disable the historical Ukraine fix
FORCE_UA_UTC3_PRE1990 = True  # set False to disable

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
    Build localized datetime using timezonefinder+pytz, then convert to UT.
    Safe regional fix:
      - If tz resolves to Europe/Kyiv (or Kiev) AND year < 1990, force UTC+3.
    """
    y, m, d = map(int, date_str.split("-"))
    hh, mm = map(int, time_str.split(":"))
    naive = datetime(y, m, d, hh, mm)

    tz_name = tf.timezone_at(lat=lat, lng=lon)

    # If tz is unknown, assume provided time is already UT
    if not tz_name:
        ut_hours = hh + mm / 60.0
        return {
            "tz_name": None,
            "utc_offset_hours": 0.0,
            "local_dt_iso": naive.isoformat(),
            "ut_dt_iso": datetime(y, m, d, hh, mm, tzinfo=pytz.UTC).isoformat(),
            "ut_hours": ut_hours
        }

    tz = pytz.timezone(tz_name)

    # Normal localization first
    try:
        local_dt = tz.localize(naive, is_dst=None)
    except Exception:
        local_dt = tz.localize(naive, is_dst=False)

    tz_label = tz.zone if hasattr(tz, "zone") else tz_name
    offset = local_dt.utcoffset() or pytz.timedelta(0)
    offset_hours = offset.total_seconds() / 3600.0

    # ---- precise & SAFE override for Ukraine in the 1980s ----
    if FORCE_UA_UTC3_PRE1990 and tz_label in ("Europe/Kyiv", "Europe/Kiev") and y < 1990:
        if abs(offset_hours - 3.0) > 1e-6:
            forced_offset = 3.0
            ut_hours = (hh + mm / 60.0) - forced_offset
            ut_dt = datetime(
                y, m, d,
                int(ut_hours) % 24,
                int((ut_hours % 1) * 60),
                tzinfo=pytz.UTC
            )
            return {
                "tz_name": f"{tz_label} (forced_UTC+3_pre1990)",
                "utc_offset_hours": forced_offset,
                "local_dt_iso": naive.isoformat(),
                "ut_dt_iso": ut_dt.isoformat(),
                "ut_hours": ut_hours
            }

    # ---- default modern path (no override) ----
    ut_dt = local_dt.astimezone(pytz.UTC)
    ut_hours = ut_dt.hour + ut_dt.minute / 60.0 + ut_dt.second / 3600.0

    return {
        "tz_name": tz_label,
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

    if not (date and time and lat and lon):
        return jsonify({"error": "Need: date, time, lat, lon"}), 400

    try:
        lat_f = float(lat)
        lon_f = float(lon)

        tzinfo = get_local_and_ut(date, time, lat_f, lon_f)
        ut = tzinfo["ut_hours"]

        y, m, d = map(int, date.split("-"))
        jd_ut = swe.julday(y, m, d, ut)

        # Houses & angles (Placidus)
        houses, ascmc = swe.houses(jd_ut, lat_f, lon_f, b"P")
        asc_deg = ascmc[0]
        mc_deg  = ascmc[1]

        asc_sign, asc_sign_deg = deg_to_sign(asc_deg)
        mc_sign,  mc_sign_deg  = deg_to_sign(mc_deg)

        # Planet positions (Sun..Pluto)
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
            res = swe.calc_ut(jd_ut, pid)
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
    port = int(os.environ.get("PORT", 8000))  # Render binds PORT
    app.run(host="0.0.0.0", port=port)
