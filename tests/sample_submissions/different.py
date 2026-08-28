"""HW3 — solved with gradient descent. Name: Henry Ives."""
import numpy as np


def gradient_descent(X, y, lr=0.01, iters=1000):
    w = np.zeros(X.shape[1])
    for _ in range(iters):
        grad = X.T @ (X @ w - y) / len(y)
        w -= lr * grad
    return w


if __name__ == '__main__':
    print(gradient_descent(np.eye(3), np.ones(3)))
