"""Small, transparent probability calibrators (fit on a dedicated calibration split)."""
from __future__ import annotations

import numpy as np
from sklearn.isotonic import IsotonicRegression
from sklearn.linear_model import LogisticRegression

_EPS = 1e-6


def _logit(p):
    p = np.clip(np.asarray(p, dtype=float), _EPS, 1 - _EPS)
    return np.log(p / (1 - p))


class IdentityCalibrator:
    method = "none"

    def fit(self, p, y):
        return self

    def transform(self, p):
        return np.asarray(p, dtype=float)


class SigmoidCalibrator:
    """Platt scaling on the logit of the raw probability."""
    method = "sigmoid"

    def fit(self, p, y):
        self._lr = LogisticRegression(C=1e6, max_iter=1000).fit(_logit(p).reshape(-1, 1), y)
        return self

    def transform(self, p):
        return self._lr.predict_proba(_logit(p).reshape(-1, 1))[:, 1]


class IsotonicCalibrator:
    method = "isotonic"

    def fit(self, p, y):
        self._iso = IsotonicRegression(out_of_bounds="clip", y_min=0.0, y_max=1.0).fit(p, y)
        return self

    def transform(self, p):
        return self._iso.predict(np.asarray(p, dtype=float))


CALIBRATORS = {"none": IdentityCalibrator, "sigmoid": SigmoidCalibrator,
               "isotonic": IsotonicCalibrator}
