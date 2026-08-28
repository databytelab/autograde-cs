"""HW3 — Linear Regression. Name: Dan Ellis."""
import numpy as np
from sklearn.metrics import r2_score


def fit(X, y, *, ridge=0.0):
    """Closed-form OLS with optional ridge penalty."""
    n = X.shape[1]
    return np.linalg.pinv(X.T @ X + ridge * np.eye(n)) @ X.T @ y


class Model:
    """Thin wrapper."""
    def __init__(self, ridge=0.0):
        self.ridge = ridge

    def train(self, X, y):
        self.w = fit(X, y, ridge=self.ridge)
        return self

    def predict(self, X):
        return X @ self.w


main()
