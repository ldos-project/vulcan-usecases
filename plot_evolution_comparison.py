#!/usr/bin/env python3
"""
Plot evolution scores comparison between baseline and Vulcan.
Shows evolution score (reward) vs iteration with best-so-far overlay.
"""

import re
import matplotlib.pyplot as plt
import numpy as np
from pathlib import Path

SYSTEM_NAME = "Thor"

def parse_log_file(log_path):
    """Parse log file and extract iteration scores."""
    data = []

    with open(log_path, 'r') as f:
        content = f.read()

    # Find all completed iterations with metrics - only successful runs
    pattern = r'Iteration (\d+):.*?runs_successfully=1\.0000.*?score=([-\d.]+).*?combined_score=([-\d.]+)'
    matches = re.findall(pattern, content, re.DOTALL)

    for match in matches:
        iteration = int(match[0])
        score = float(match[1])  # This is the negative cost

        # Skip if score is exactly 0 (failed runs sometimes have this)
        if score == 0.0:
            continue

        data.append((iteration, score))

    # Sort by iteration number to handle out-of-order logging
    data.sort(key=lambda x: x[0])

    # Now compute best-so-far
    iterations = []
    scores = []
    best_scores = []
    current_best_score = float('-inf')

    for iteration, score in data:
        # Update best score found so far (higher score = lower cost = better)
        current_best_score = max(current_best_score, score)

        iterations.append(iteration)
        scores.append(score)
        best_scores.append(current_best_score)

    return np.array(iterations), np.array(scores), np.array(best_scores)

def main():
    # Paths to log files
    baseline_log = Path("./cbl_results/adrs_openevolve/logs/openevolve_20260424_181801.log")
    thor_log = Path("./cbl_results/vulcan/logs/openevolve_20260429_192904.log")

    print("Parsing baseline log...")
    base_iter, base_scores, base_best = parse_log_file(baseline_log)
    print(f"  Found {len(base_iter)} iterations")
    print(f"  Score range: {base_scores.min():.2f} to {base_scores.max():.2f}")
    print(f"  Final best: {base_best[-1]:.2f}")

    print(f"\nParsing {SYSTEM_NAME} log...")
    thor_iter, thor_scores, thor_best = parse_log_file(thor_log)
    print(f"  Found {len(thor_iter)} iterations")
    print(f"  Score range: {thor_scores.min():.2f} to {thor_scores.max():.2f}")
    print(f"  Final best: {thor_best[-1]:.2f}")

    # Convert to positive cost (negate the scores)
    base_scores_cost = -base_scores
    base_best_cost = -base_best
    thor_scores_cost = -thor_scores
    thor_best_cost = -thor_best

    # Create the plot (more square-ish)
    fig, ax = plt.subplots(figsize=(10, 8))

    # Use colorblind-friendly colors with different line styles for accessibility
    baseline_color = '#1f77b4'  # Blue
    thor_color = '#ff7f0e'  # Orange

    # Plot evolution scores (individual iteration scores)
    # Use different markers for B&W distinguishability
    ax.plot(base_iter, base_scores_cost, 'o', alpha=0.25,
            color=baseline_color, markersize=5)
    ax.plot(thor_iter, thor_scores_cost, 's', alpha=0.25,
            color=thor_color, markersize=5)

    # Plot best-so-far lines (thick, prominent, different line styles for B&W)
    ax.plot(base_iter, base_best_cost, linewidth=5, label='ADRS (best so far)',
            color=baseline_color, linestyle='-', alpha=0.9)
    ax.plot(thor_iter, thor_best_cost, linewidth=5, label=f'{SYSTEM_NAME} (best so far)',
            color=thor_color, linestyle='--', alpha=0.9, dashes=(5, 3))

    # Formatting with increased font sizes (30-50% larger)
    ax.set_xlabel('Iteration', fontsize=36, fontweight='bold')
    ax.set_ylabel('Cost (lower is better)', fontsize=36, fontweight='bold')
    # ax.set_title('Evolution progress: ADRS vs Thor', fontsize=22, fontweight='bold', pad=35)

    # Increase tick label font sizes
    ax.tick_params(axis='both', which='major', labelsize=36)

    # Set custom yticks with reduced spacing
    ax.set_yticks(np.arange(84, 103, 4))  # Every 2 units instead of default spacing

    # Legend at top center with two columns and larger marker size
    legend = ax.legend(loc='upper center', bbox_to_anchor=(0.5, 1.0),
                      ncol=1, fontsize=36, framealpha=0.95, markerscale=2)

    ax.grid(True, alpha=0.8, linestyle='--', linewidth=0.8)

    # Set y-limits to specified range
    ax.set_ylim(102, 84)  # Inverted so lower is at top (visually better)

    # Add text annotations for final scores (moved left and slightly up)
    # ax.annotate(f'Final: {base_best_cost[-1]:.2f}',
    #             xy=(base_iter[-1], base_best_cost[-1]),
    #             xytext=(-50, 14), textcoords='offset points',
    #             fontsize=20, color=baseline_color, fontweight='bold',
    #             bbox=dict(boxstyle='round,pad=0.5', facecolor='white', edgecolor=baseline_color, alpha=0.9))
    # ax.annotate(f'Final: {thor_best_cost[-1]:.2f}',
    #             xy=(thor_iter[-1], thor_best_cost[-1]),
    #             xytext=(-45, 16), textcoords='offset points',
    #             fontsize=20, color=thor_color, fontweight='bold',
    #             bbox=dict(boxstyle='round,pad=0.5', facecolor='white', edgecolor=thor_color, alpha=0.9))

    plt.tight_layout()

    # Save the plot
    plt.savefig("./evolution-comparison-cbl.svg", bbox_inches='tight')
    print(f"\nPlot saved to: ./evolution-comparison-cbl.svg")

    # Show the plot
    plt.show()

    # Print summary statistics (in terms of cost)
    print("\n=== SUMMARY ===")
    print(f"\nBaseline:")
    print(f"  Initial best cost: {-base_best[0]:.2f}")
    print(f"  Final best cost: {-base_best[-1]:.2f}")
    print(f"  Improvement: {-base_best[0] - (-base_best[-1]):.2f} (reduction in cost)")

    print(f"\n{SYSTEM_NAME}:")
    print(f"  Initial best cost: {-thor_best[0]:.2f}")
    print(f"  Final best cost: {-thor_best[-1]:.2f}")
    print(f"  Improvement: {-thor_best[0] - (-thor_best[-1]):.2f} (reduction in cost)")

    print(f"\n{SYSTEM_NAME} vs Baseline:")
    print(f"  Final cost difference: {(-thor_best[-1]) - (-base_best[-1]):.2f} (negative = Thor better)")
    if base_best[-1] != 0:
        pct_improvement = ((-base_best[-1]) - (-thor_best[-1])) / (-base_best[-1]) * 100
        print(f"  Relative improvement: {pct_improvement:.2f}%")

if __name__ == "__main__":
    main()
