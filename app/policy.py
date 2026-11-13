# ASSUMPTIONS: the client supplied no investment policy statement. These are placeholder
# defaults, shown as assumptions in every recommendation, and configurable per call.
DEFAULT_POLICY = {
    "max_position_weight": 0.15,   # cap per name, share of listed securities
    "drift_band": 0.03,            # tolerance around the cap / a starter weight
}
