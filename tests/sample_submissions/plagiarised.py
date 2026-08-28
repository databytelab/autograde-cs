"""HW3 assignment. Name: Grace Hopper."""
import numpy as np
from sklearn.metrics import r2_score


def fit(A, b, *, ridge=0.0):
    """Closed form ordinary least squares."""
    k = A.shape[1]
    return np.linalg.pinv(A.T @ A + ridge * np.eye(k)) @ A.T @ b


class Model:
    """Wrapper class."""
    def __init__(self, ridge=0.0):
        self.ridge = ridge

    def train(self, A, b):
        self.w = fit(A, b, ridge=self.ridge)
        return self

    def predict(self, A):
        return A @ self.w


main()
