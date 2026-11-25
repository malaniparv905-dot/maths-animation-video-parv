#!/usr/bin/env python3
"""
Mathematical Verification Script for M3 Linear Algebra & Calculus IA
Student: Parv Malani (E25B070827, Batch: Ramanujan)
Topic: Gaussian Elimination — Solving a 3x3 System of Linear Equations

This script independently verifies using NumPy:
1. The ACTUAL 3x3 system depicted in the existing animation video
   (Campus Cafe & Mess Pricing Mystery: x + y = 5, x + z = 8, y + z = 7).
2. Every elementary row operation and back-substitution step shown in the video.
3. Also verifies the alternate 3x3 system listed in the project prompt brief
   (x + y + z = 6, 2x + 3y + z = 11, x + 2y + 3z = 14) for completeness and
   documents the mismatch between the brief and the actual video.
"""

import numpy as np


def verify_video_system() -> dict:
    """Verify the Campus Cafe system actually animated in the video."""
    print("=" * 72)
    print("1. VERIFICATION OF ACTUAL VIDEO SYSTEM (Campus Cafe & Mess)")
    print("=" * 72)
    # System:
    #   Order #101: Coffee (x) + Tea (y) = 5       -> 1x + 1y + 0z = 5
    #   Order #102: Coffee (x) + Sandwich (z) = 8  -> 1x + 0y + 1z = 8
    #   Order #103: Tea (y) + Sandwich (z) = 7     -> 0x + 1y + 1z = 7
    A = np.array([[1.0, 1.0, 0.0],
                  [1.0, 0.0, 1.0],
                  [0.0, 1.0, 1.0]])
    b = np.array([5.0, 8.0, 7.0])

    det_A = float(np.linalg.det(A))
    rank_A = int(np.linalg.matrix_rank(A))
    sol = np.linalg.solve(A, b)
    x, y, z = sol

    print(f"Coefficient matrix A:\n{A}")
    print(f"RHS vector b: {b}")
    print(f"det(A) = {det_A:.6f} (nonzero => unique solution exists)")
    print(f"rank(A) = {rank_A}")
    print(f"NumPy linalg.solve solution: x (Coffee) = {x:.6g}, y (Tea) = {y:.6g}, z (Sandwich) = {z:.6g}")

    assert np.allclose(sol, [3.0, 2.0, 5.0]), f"Unexpected solution: {sol}"
    assert np.allclose(A @ sol, b), "A @ x != b"

    # Step-by-step row operations matching the animation (170s - 262s)
    M = np.hstack([A, b.reshape(-1, 1)])
    print("\n--- Step-by-Step Row Operations (Matching Video 02:50 - 04:22) ---")
    print("Initial Augmented Matrix [A | b]:\n", M)

    # Step 1 (170s - 194s): R2 <- R2 - R1
    M[1] = M[1] - M[0]
    expected_1 = np.array([0.0, -1.0, 1.0, 3.0])
    assert np.allclose(M[1], expected_1)
    print("\nStep 1 (R2 <- R2 - R1):\n", M)

    # Step 2 (194s - 214s): R2 <- (-1) * R2
    M[1] = (-1.0) * M[1]
    expected_2 = np.array([0.0, 1.0, -1.0, -3.0])
    assert np.allclose(M[1], expected_2)
    print("\nStep 2 (R2 <- (-1) * R2):\n", M)

    # Step 3 (214s - 238s): R3 <- R3 - R2
    M[2] = M[2] - M[1]
    expected_3 = np.array([0.0, 0.0, 2.0, 10.0])
    assert np.allclose(M[2], expected_3)
    print("\nStep 3 (R3 <- R3 - R2):\n", M)

    # Step 4 (238s - 254s): R3 <- (1/2) * R3 -> Row Echelon Form (REF)
    M[2] = 0.5 * M[2]
    expected_ref = np.array([
        [1.0, 1.0, 0.0, 5.0],
        [0.0, 1.0, -1.0, -3.0],
        [0.0, 0.0, 1.0, 5.0],
    ])
    assert np.allclose(M, expected_ref)
    print("\nStep 4 (R3 <- (1/2) * R3) [REF Achieved]:\n", M)

    # Step 5 (254s - 262s): Back-substitution to RREF
    # Sequential order: first R2 <- R2 + R3, then R1 <- R1 - R2
    M[1] = M[1] + M[2]
    M[0] = M[0] - M[1]
    expected_rref = np.array([
        [1.0, 0.0, 0.0, 3.0],
        [0.0, 1.0, 0.0, 2.0],
        [0.0, 0.0, 1.0, 5.0],
    ])
    assert np.allclose(M, expected_rref)
    print("\nStep 5 (R2 <- R2 + R3, then R1 <- R1 - R2) [RREF Achieved]:\n", M)

    # Check original orders
    assert np.isclose(x + y, 5.0)
    assert np.isclose(x + z, 8.0)
    assert np.isclose(y + z, 7.0)
    print("\nOrder Verification:")
    print(f"  Order 1 (x + y = 5): {x:.0f} + {y:.0f} = {x + y:.0f} [PASS]")
    print(f"  Order 2 (x + z = 8): {x:.0f} + {z:.0f} = {x + z:.0f} [PASS]")
    print(f"  Order 3 (y + z = 7): {y:.0f} + {z:.0f} = {y + z:.0f} [PASS]")

    return {"det": det_A, "rank": rank_A, "solution": (float(x), float(y), float(z))}


def verify_prompt_brief_system() -> dict:
    """Verify the secondary system mentioned in Section 5 of the prompt brief."""
    print("\n" + "=" * 72)
    print("2. VERIFICATION OF PROMPT-BRIEF REFERENCE SYSTEM (Not in Video)")
    print("=" * 72)
    A = np.array([[1.0, 1.0, 1.0],
                  [2.0, 3.0, 1.0],
                  [1.0, 2.0, 3.0]])
    b = np.array([6.0, 11.0, 14.0])
    sol = np.linalg.solve(A, b)
    det_A = float(np.linalg.det(A))
    assert np.allclose(sol, [1.0, 2.0, 3.0])

    M = np.hstack([A, b.reshape(-1, 1)])
    M[1] = M[1] - 2.0 * M[0]
    M[2] = M[2] - M[0]
    M[2] = M[2] - M[1]
    expected_ref = np.array([
        [1.0, 1.0, 1.0, 6.0],
        [0.0, 1.0, -1.0, -1.0],
        [0.0, 0.0, 3.0, 9.0],
    ])
    assert np.allclose(M, expected_ref)
    print(f"det(A) = {det_A:.6f}")
    print(f"REF Matrix:\n{M}")
    print(f"Solution: (x, y, z) = ({sol[0]:.0f}, {sol[1]:.0f}, {sol[2]:.0f}) [PASS]")
    print("NOTE: This system is mathematically valid, but is NOT the system shown in the video.")
    return {"det": det_A, "solution": tuple(float(v) for v in sol)}


if __name__ == "__main__":
    res_video = verify_video_system()
    res_brief = verify_prompt_brief_system()
    print("\n" + "=" * 72)
    print("ALL MATHEMATICAL VERIFICATION CHECKS PASSED SUCCESSFULLY.")
    print("=" * 72)
