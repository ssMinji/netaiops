#!/usr/bin/env python3
"""
HTML Report Generator for AgentCore Evaluation Framework

This script generates comprehensive HTML reports with interactive dashboards,
charts, and detailed analysis from evaluation results.
"""

import argparse
import json
import os
import sys
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Any, List, Optional
import base64

# Add parent directory to path for imports
sys.path.append(str(Path(__file__).parent.parent))

# Template for HTML report
HTML_TEMPLATE = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>AgentCore Evaluation Score Card</title>
    <script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
    <style>
        * {
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }

        body {
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Oxygen, Ubuntu, Cantarell, sans-serif;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            min-height: 100vh;
            color: #333;
        }

        .container {
            max-width: 1400px;
            margin: 0 auto;
            padding: 20px;
        }

        .header {
            background: rgba(255, 255, 255, 0.95);
            backdrop-filter: blur(10px);
            border-radius: 20px;
            padding: 30px;
            margin-bottom: 30px;
            box-shadow: 0 20px 40px rgba(0, 0, 0, 0.1);
            text-align: center;
        }

        .header h1 {
            color: #2c3e50;
            font-size: 2.5rem;
            margin-bottom: 10px;
            font-weight: 700;
        }

        .header .subtitle {
            color: #7f8c8d;
            font-size: 1.2rem;
            margin-bottom: 20px;
        }

        .header .timestamp {
            background: #e3f2fd;
            color: #1976d2;
            padding: 8px 16px;
            border-radius: 20px;
            display: inline-block;
            font-weight: 500;
        }

        .metrics-grid {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(250px, 1fr));
            gap: 20px;
            margin-bottom: 30px;
        }

        .metric-card {
            background: rgba(255, 255, 255, 0.95);
            backdrop-filter: blur(10px);
            border-radius: 15px;
            padding: 25px;
            text-align: center;
            box-shadow: 0 10px 30px rgba(0, 0, 0, 0.1);
            transition: all 0.3s ease;
        }

        .metric-card:hover {
            transform: translateY(-5px);
            box-shadow: 0 20px 40px rgba(0, 0, 0, 0.15);
        }

        .metric-value {
            font-size: 2.5rem;
            font-weight: 700;
            margin-bottom: 5px;
        }

        .metric-label {
            color: #666;
            font-size: 0.9rem;
            text-transform: uppercase;
            letter-spacing: 1px;
        }

        .success { color: #27ae60; }
        .warning { color: #f39c12; }
        .danger { color: #e74c3c; }
        .info { color: #3498db; }

        .main-dashboard-grid {
            display: grid;
            grid-template-columns: 1fr;
            gap: 30px;
            margin-bottom: 30px;
            align-items: start;
        }

        .charts-grid {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(500px, 1fr));
            gap: 30px;
            margin-bottom: 30px;
        }

        .chart-container {
            background: rgba(255, 255, 255, 0.95);
            backdrop-filter: blur(10px);
            border-radius: 15px;
            padding: 25px;
            box-shadow: 0 10px 30px rgba(0, 0, 0, 0.1);
            height: 400px;
            position: relative;
            display: flex;
            flex-direction: column;
            justify-content: center;
            align-items: center;
        }

        .chart-title {
            font-size: 1.3rem;
            font-weight: 600;
            margin-bottom: 20px;
            color: #2c3e50;
            text-align: center;
        }

        .chart-canvas {
            height: 300px !important;
            width: 100% !important;
        }

        .agents-grid {
            display: grid;
            grid-template-columns: 1fr;
            gap: 25px;
            width: 100%;
            justify-content: stretch;
        }

        .agent-card {
            background: rgba(255, 255, 255, 0.95);
            backdrop-filter: blur(10px);
            border-radius: 15px;
            padding: 20px;
            box-shadow: 0 10px 30px rgba(0, 0, 0, 0.1);
            min-height: 400px;
            display: flex;
            flex-direction: column;
            justify-content: flex-start;
        }

        .agent-header {
            display: flex;
            align-items: center;
            justify-content: space-between;
            margin-bottom: 20px;
            padding-bottom: 15px;
            border-bottom: 2px solid #ecf0f1;
            gap: 15px;
            flex-wrap: wrap;
        }

        .agent-name {
            font-size: 1.4rem;
            font-weight: 600;
            color: #2c3e50;
            flex: 1 1 auto;
            min-width: 0;
            word-break: break-word;
        }

        .agent-score {
            font-size: 1.8rem;
            font-weight: 700;
            padding: 8px 16px;
            border-radius: 10px;
            background: #e8f5e8;
            color: #27ae60;
            flex: 0 0 auto;
            white-space: nowrap;
        }

        .agent-score.warning {
            background: #fef3e2;
            color: #f39c12;
        }

        .agent-score.danger {
            background: #fdeaea;
            color: #e74c3c;
        }

        .agent-details {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(150px, 1fr));
            gap: 15px;
            margin-bottom: 20px;
        }

        .detail-item {
            text-align: center;
            padding: 15px;
            background: #f8f9fa;
            border-radius: 10px;
        }

        .detail-value {
            font-size: 1.2rem;
            font-weight: 600;
            margin-bottom: 5px;
        }

        .detail-label {
            font-size: 0.8rem;
            color: #666;
            text-transform: uppercase;
            letter-spacing: 0.5px;
        }

        .evaluation-criteria {
            background: #f8f9fa;
            border-radius: 10px;
            padding: 15px;
            margin-top: 15px;
            border-left: 4px solid #3498db;
        }

        .evaluation-criteria h4 {
            color: #2c3e50;
            margin-bottom: 12px;
            font-size: 0.9rem;
            font-weight: 600;
            text-transform: uppercase;
            letter-spacing: 0.5px;
        }

        .criteria-list {
            display: grid;
            gap: 8px;
        }

        .criteria-item {
            display: flex;
            align-items: flex-start;
            gap: 8px;
            font-size: 0.8rem;
            line-height: 1.4;
        }

        .criteria-label {
            font-weight: 600;
            color: #3498db;
            min-width: 85px;
            flex-shrink: 0;
        }

        .criteria-description {
            color: #555;
        }

        .detailed-results {
            background: rgba(255, 255, 255, 0.95);
            backdrop-filter: blur(10px);
            border-radius: 15px;
            padding: 30px;
            box-shadow: 0 10px 30px rgba(0, 0, 0, 0.1);
            margin-bottom: 30px;
            overflow-x: auto;
        }

        .detailed-results h2 {
            color: #2c3e50;
            margin-bottom: 25px;
            font-size: 1.6rem;
            text-align: center;
        }

        .table-container {
            overflow-x: auto;
            margin-top: 20px;
            border-radius: 10px;
            box-shadow: 0 2px 8px rgba(0, 0, 0, 0.1);
        }

        .results-table {
            width: 100%;
            min-width: 1300px;
            border-collapse: collapse;
            background: white;
            border-radius: 10px;
            overflow: hidden;
        }

        .results-table th,
        .results-table td {
            padding: 12px 10px;
            text-align: left;
            border-bottom: 1px solid #e3e6ea;
            border-right: 1px solid #e3e6ea;
            font-size: 0.9rem;
            line-height: 1.4;
        }

        .results-table th:last-child,
        .results-table td:last-child {
            border-right: none;
        }

        .results-table th {
            background: linear-gradient(135deg, #f8f9fa 0%, #e9ecef 100%);
            font-weight: 600;
            color: #2c3e50;
            text-transform: uppercase;
            font-size: 0.8rem;
            letter-spacing: 0.5px;
            position: sticky;
            top: 0;
            z-index: 10;
            box-shadow: 0 2px 4px rgba(0, 0, 0, 0.1);
        }

        .results-table tr:hover {
            background: #f8f9fa;
            transition: background-color 0.2s ease;
        }

        .results-table tr:nth-child(even) {
            background: rgba(248, 249, 250, 0.3);
        }

        .results-table tr:nth-child(even):hover {
            background: #f8f9fa;
        }

        /* Test # column */
        .results-table td:nth-child(1),
        .results-table th:nth-child(1) {
            min-width: 60px;
            width: 60px;
            text-align: center;
            font-weight: 600;
        }

        /* Test Scenario column */
        .results-table td:nth-child(2),
        .results-table th:nth-child(2) {
            min-width: 200px;
            max-width: 250px;
        }

        /* Agent column */
        .results-table td:nth-child(3),
        .results-table th:nth-child(3) {
            min-width: 120px;
            width: 120px;
        }

        /* Score columns (Overall, Helpfulness, Accuracy, Clarity, Professionalism, Completeness) */
        .results-table td:nth-child(n+4):nth-child(-n+9),
        .results-table th:nth-child(n+4):nth-child(-n+9) {
            min-width: 80px;
            width: 80px;
            text-align: center;
        }

        /* Response Time column */
        .results-table td:nth-child(10),
        .results-table th:nth-child(10) {
            min-width: 100px;
            width: 100px;
            text-align: center;
        }

        .status-badge {
            padding: 4px 12px;
            border-radius: 15px;
            font-size: 0.8rem;
            font-weight: 500;
            text-transform: uppercase;
            letter-spacing: 0.5px;
        }

        .status-success {
            background: #e8f5e8;
            color: #27ae60;
        }

        .status-warning {
            background: #fef3e2;
            color: #f39c12;
        }

        .status-error {
            background: #fdeaea;
            color: #e74c3c;
        }

        .recommendations {
            background: rgba(255, 255, 255, 0.95);
            backdrop-filter: blur(10px);
            border-radius: 15px;
            padding: 30px;
            box-shadow: 0 10px 30px rgba(0, 0, 0, 0.1);
        }

        .recommendations h2 {
            color: #2c3e50;
            margin-bottom: 20px;
            font-size: 1.6rem;
        }

        .recommendation-item {
            background: #f8f9fa;
            border-left: 4px solid #3498db;
            padding: 15px 20px;
            margin-bottom: 15px;
            border-radius: 0 10px 10px 0;
        }

        .recommendation-priority {
            font-weight: 600;
            margin-bottom: 8px;
            text-transform: uppercase;
            font-size: 0.85rem;
            letter-spacing: 0.5px;
        }

        .priority-high {
            color: #e74c3c;
        }

        .priority-medium {
            color: #f39c12;
        }

        .priority-low {
            color: #27ae60;
        }

        .priority-info {
            color: #3498db;
        }

        .criteria-guidance {
            border-left: 4px solid #2c3e50 !important;
            background: #f8f9fa !important;
        }

        .criteria-title {
            font-weight: 600;
            margin-bottom: 10px;
            color: #2c3e50;
            font-size: 1.1rem;
        }

        .criteria-details {
            color: #555;
            margin-bottom: 15px;
            font-style: italic;
        }

        .criteria-next-steps {
            background: white;
            padding: 15px;
            border-radius: 8px;
            margin-top: 10px;
        }

        .next-step {
            margin: 5px 0;
            padding-left: 10px;
            color: #2c3e50;
            line-height: 1.4;
        }

        .footer {
            text-align: center;
            margin-top: 40px;
            padding: 20px;
            color: rgba(255, 255, 255, 0.8);
        }

        /* Tooltip Styles */
        .tooltip {
            position: relative;
            cursor: help;
            border-bottom: 1px dotted #666;
        }

        .tooltip::before {
            content: attr(data-tooltip);
            position: absolute;
            bottom: 125%;
            left: 50%;
            transform: translateX(-50%);
            background: rgba(0, 0, 0, 0.9);
            color: white;
            padding: 8px 12px;
            border-radius: 6px;
            font-size: 0.85rem;
            white-space: nowrap;
            max-width: 250px;
            white-space: normal;
            width: max-content;
            max-width: 300px;
            z-index: 1000;
            opacity: 0;
            visibility: hidden;
            transition: opacity 0.3s, visibility 0.3s;
            pointer-events: none;
            box-shadow: 0 4px 12px rgba(0, 0, 0, 0.15);
        }

        .tooltip::after {
            content: '';
            position: absolute;
            bottom: 115%;
            left: 50%;
            transform: translateX(-50%);
            border: 5px solid transparent;
            border-top-color: rgba(0, 0, 0, 0.9);
            opacity: 0;
            visibility: hidden;
            transition: opacity 0.3s, visibility 0.3s;
        }

        .tooltip:hover::before,
        .tooltip:hover::after {
            opacity: 1;
            visibility: visible;
        }

        @media (max-width: 768px) {
            .container {
                padding: 10px;
            }

            .main-dashboard-grid {
                grid-template-columns: 1fr;
                gap: 20px;
            }

            .agents-grid {
                grid-template-columns: 1fr;
            }

            .charts-grid {
                grid-template-columns: 1fr;
            }

            .chart-container {
                padding: 15px;
            }

            .agents-grid {
                grid-template-columns: 1fr;
            }

            .metrics-grid {
                grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
            }
        }

        .loading {
            display: flex;
            justify-content: center;
            align-items: center;
            min-height: 200px;
            font-size: 1.2rem;
            color: #666;
        }

        .error-message {
            background: #fdeaea;
            color: #e74c3c;
            padding: 20px;
            border-radius: 10px;
            margin: 20px 0;
            text-align: center;
        }
    </style>
</head>
<body>
    <div class="container">
        <!-- Header -->
        <div class="header">
            <h1>🎯 AgentCore Evaluation Score Card</h1>
            <div class="subtitle">Comprehensive AI Agent Performance Analysis</div>
            <div class="timestamp" id="timestamp">{{TIMESTAMP}}</div>
        </div>

        <!-- Main Dashboard Row -->
        <div class="main-dashboard-grid">
            <!-- Agent Performance Chart -->
            <div class="chart-container">
                <div class="chart-title">Agent Performance</div>
                <canvas id="performanceChart" class="chart-canvas"></canvas>
            </div>

            <!-- Individual Agent Results -->
            <div class="agents-grid" id="agent-results">
                <!-- Agent cards will be dynamically generated -->
            </div>
        </div>

        <!-- Detailed Results Table -->
        <div class="detailed-results">
            <h2>📊 Detailed Test Results</h2>
            <div class="table-container">
                <table class="results-table" id="results-table">
                    <thead>
                        <tr>
                            <th>Test #</th>
                            <th>Test Scenario</th>
                            <th>Agent</th>
                            <th>Overall Score</th>
                            <th class="tooltip" data-tooltip="How well the agent addresses user needs and provides actionable solutions">Helpfulness</th>
                            <th class="tooltip" data-tooltip="Correctness of technical information and recommendations provided">Accuracy</th>
                            <th class="tooltip" data-tooltip="How clear, organized, and easy to understand the agent's responses are">Clarity</th>
                            <th class="tooltip" data-tooltip="Appropriate technical language, tone, and communication style">Professionalism</th>
                            <th class="tooltip" data-tooltip="Thoroughness in addressing all aspects of the user's query">Completeness</th>
                            <th>Response Time</th>
                        </tr>
                    </thead>
                    <tbody id="results-tbody">
                        <!-- Results will be dynamically populated -->
                    </tbody>
                </table>
            </div>
        </div>

        <!-- Recommendations Section -->
        <div class="recommendations">
            <h2>💡 Recommendations & Next Steps</h2>
            <div id="recommendations-content">
                <!-- Recommendations will be dynamically generated -->
            </div>
        </div>

        <div class="footer">
            <p>Generated by AgentCore Evaluation Framework | AWS Account: {{ACCOUNT_ID}} | Region: {{REGION}}</p>
        </div>
    </div>

    <script>
        // Evaluation data (injected by Python script)
        const evaluationData = {{EVALUATION_DATA}};

        // Initialize charts and dashboard
        document.addEventListener('DOMContentLoaded', function() {
            console.log('DOM loaded, initializing dashboard...');
            console.log('Evaluation data:', evaluationData);
            try {
                console.log('Initializing charts...');
                initializeCharts();
                console.log('Populating agent cards...');
                populateAgentCards();
                console.log('Populating results table...');
                populateResultsTable();
                console.log('Generating recommendations...');
                generateRecommendations();
                console.log('Dashboard initialization complete');
            } catch (error) {
                console.error('Error initializing dashboard:', error);
                showErrorMessage('Failed to load evaluation data: ' + error.message);
            }
        });

        function initializeCharts() {
            try {
                console.log('Getting performance chart canvas...');
                const performanceCanvas = document.getElementById('performanceChart');
                if (!performanceCanvas) {
                    throw new Error('Performance chart canvas not found');
                }
                
                console.log('Generating performance datasets...');
                const performanceDatasets = generatePerformanceDatasets();
                console.log('Performance datasets:', performanceDatasets);
                
                const performanceCtx = performanceCanvas.getContext('2d');
                console.log('Creating performance chart...');
                const performanceChart = new Chart(performanceCtx, {
                    type: 'radar',
                    data: {
                        labels: ['Helpfulness', 'Accuracy', 'Clarity', 'Professionalism', 'Completeness'],
                        datasets: performanceDatasets
                    },
                    options: {
                        responsive: true,
                        maintainAspectRatio: false,
                        scales: {
                            r: {
                                beginAtZero: true,
                                max: 5,
                                stepSize: 1
                            }
                        },
                        plugins: {
                            legend: {
                                position: 'bottom'
                            }
                        }
                    }
                });

                
                console.log('Charts initialized successfully');
            } catch (error) {
                console.error('Error initializing charts:', error);
                throw error;
            }
        }

        function generatePerformanceDatasets() {
            const colors = ['#e74c3c', '#3498db', '#27ae60'];
            const datasets = [];
            
            Object.keys(evaluationData.detailed_results || {}).forEach((agentName, index) => {
                const agentData = evaluationData.detailed_results[agentName];
                const judgeEval = agentData.judge_evaluation || {};
                const scores = judgeEval.aggregate_scores || {};
                
                datasets.push({
                    label: agentName,
                    data: [
                        scores.helpfulness?.score || 0,
                        scores.accuracy?.score || 0,
                        scores.clarity?.score || 0,
                        scores.professionalism?.score || 0,
                        scores.completeness?.score || 0
                    ],
                    borderColor: colors[index % colors.length],
                    backgroundColor: colors[index % colors.length] + '20',
                    pointBackgroundColor: colors[index % colors.length]
                });
            });
            
            return datasets;
        }


        function populateAgentCards() {
            const agentResults = document.getElementById('agent-results');
            
            Object.entries(evaluationData.detailed_results || {}).forEach(([agentName, agentData]) => {
                const judgeEval = agentData.judge_evaluation || {};
                const overallScore = judgeEval.overall_score || 0;
                const scoreClass = 'info';  // Use consistent 'info' class for all scores
                const aggregateScores = judgeEval.aggregate_scores || {};
                
                const agentCard = document.createElement('div');
                agentCard.className = 'agent-card';
                agentCard.innerHTML = `
                    <div class="agent-header">
                        <div class="agent-name">${agentName}</div>
                        <div class="agent-score ${scoreClass}">${overallScore.toFixed(1)}/5.0</div>
                    </div>
                    <div class="agent-details">
                        <div class="detail-item">
                            <div class="detail-value">${aggregateScores.helpfulness?.score?.toFixed(1) || 'N/A'}</div>
                            <div class="detail-label tooltip" data-tooltip="How well the agent addresses user needs and provides actionable solutions">Helpfulness</div>
                        </div>
                        <div class="detail-item">
                            <div class="detail-value">${aggregateScores.accuracy?.score?.toFixed(1) || 'N/A'}</div>
                            <div class="detail-label tooltip" data-tooltip="Correctness of technical information and recommendations provided">Accuracy</div>
                        </div>
                        <div class="detail-item">
                            <div class="detail-value">${aggregateScores.clarity?.score?.toFixed(1) || 'N/A'}</div>
                            <div class="detail-label tooltip" data-tooltip="How clear, organized, and easy to understand the agent's responses are">Clarity</div>
                        </div>
                        <div class="detail-item">
                            <div class="detail-value">${aggregateScores.professionalism?.score?.toFixed(1) || 'N/A'}</div>
                            <div class="detail-label tooltip" data-tooltip="Appropriate technical language, tone, and communication style">Professionalism</div>
                        </div>
                        <div class="detail-item">
                            <div class="detail-value">${aggregateScores.completeness?.score?.toFixed(1) || 'N/A'}</div>
                            <div class="detail-label tooltip" data-tooltip="Thoroughness in addressing all aspects of the user's query">Completeness</div>
                        </div>
                        <div class="detail-item">
                            <div class="detail-value">${agentData.runtime_arn ? 'Connected' : 'Disconnected'}</div>
                            <div class="detail-label">Status</div>
                        </div>
                    </div>
                    <div class="evaluation-criteria">
                        <h4>📋 Evaluation Criteria</h4>
                        <div class="criteria-list">
                            <div class="criteria-item">
                                <span class="criteria-label">Helpfulness:</span>
                                <span class="criteria-description">Addresses user needs and provides actionable solutions</span>
                            </div>
                            <div class="criteria-item">
                                <span class="criteria-label">Accuracy:</span>
                                <span class="criteria-description">Correctness of technical information and recommendations</span>
                            </div>
                            <div class="criteria-item">
                                <span class="criteria-label">Clarity:</span>
                                <span class="criteria-description">Clear, organized, and easy to understand responses</span>
                            </div>
                            <div class="criteria-item">
                                <span class="criteria-label">Professional:</span>
                                <span class="criteria-description">Appropriate technical language, tone, and communication style</span>
                            </div>
                            <div class="criteria-item">
                                <span class="criteria-label">Completeness:</span>
                                <span class="criteria-description">Thoroughness in addressing all aspects of the query</span>
                            </div>
                        </div>
                    </div>
                `;
                
                agentResults.appendChild(agentCard);
            });
        }

        function populateResultsTable() {
            const tbody = document.getElementById('results-tbody');
            let testNumber = 1;
            
            Object.entries(evaluationData.detailed_results || {}).forEach(([agentName, agentData]) => {
                const judgeEval = agentData.judge_evaluation || {};
                const testResults = agentData.workflow?.test_results || [];
                const judgeEvaluations = judgeEval.judge_evaluations || [];
                
                // Create a row for each individual test case
                testResults.forEach((testResult, index) => {
                    const testCaseId = testResult.test_case_id || `test_${index + 1}`;
                    const query = testResult.query || 'N/A';
                    const responseTime = testResult.response_time || 0;
                    
                    // Find corresponding judge evaluation for this test case
                    const testJudgeEval = judgeEvaluations.find(eval => eval.test_case_id === testCaseId);
                    const testScore = testJudgeEval?.overall_score || 0;
                    
                    const statusClass = 'info';  // Use consistent 'info' class for all test results
                    const statusText = 'Completed';  // Consistent status text
                    
                    // Format test scenario name
                    const scenarioName = testCaseId.replace(/_/g, ' ')
                        .replace(/\\b\\w/g, l => l.toUpperCase())
                        .replace('Basic', 'Basic Analysis')
                        .replace('Retransmission', 'TCP Retransmission')
                        .replace('Dns', 'DNS Troubleshooting');
                    
                    // Get individual test case scores from the specific judge evaluation
                    const testScores = testJudgeEval?.scores || {};
                    const helpfulnessScore = testScores.helpfulness?.score || 0;
                    const accuracyScore = testScores.accuracy?.score || 0;
                    const clarityScore = testScores.clarity?.score || 0;
                    const professionalismScore = testScores.professionalism?.score || 0;
                    const completenessScore = testScores.completeness?.score || 0;
                    
                    // Consistent color coding for all dimension scores
                    const getScoreColor = (score) => {
                        return '#2c3e50';  // Consistent dark blue-gray for all values
                    };

                    const row = document.createElement('tr');
                    row.innerHTML = `
                        <td>${testNumber}</td>
                        <td>
                            <div style="font-weight: 600; margin-bottom: 5px;">${scenarioName}</div>
                            <div style="font-size: 0.9em; color: #666; font-style: italic;">"${query}"</div>
                        </td>
                        <td>${agentName}</td>
                        <td>${testScore.toFixed(2)}/5.0</td>
                        <td style="color: ${getScoreColor(helpfulnessScore)}; font-weight: 600;">${helpfulnessScore.toFixed(1)}/5.0</td>
                        <td style="color: ${getScoreColor(accuracyScore)}; font-weight: 600;">${accuracyScore.toFixed(1)}/5.0</td>
                        <td style="color: ${getScoreColor(clarityScore)}; font-weight: 600;">${clarityScore.toFixed(1)}/5.0</td>
                        <td style="color: ${getScoreColor(professionalismScore)}; font-weight: 600;">${professionalismScore.toFixed(1)}/5.0</td>
                        <td style="color: ${getScoreColor(completenessScore)}; font-weight: 600;">${completenessScore.toFixed(1)}/5.0</td>
                        <td>${responseTime.toFixed(2)}s</td>
                    `;
                    
                    tbody.appendChild(row);
                    testNumber++;
                });
            });
        }

        function generateRecommendations() {
            const recommendationsContent = document.getElementById('recommendations-content');
            const recommendations = [];
            
            // Collect all low-scoring dimensions from all agents
            const lowScoringDimensions = new Set();
            Object.entries(evaluationData.detailed_results || {}).forEach(([agentName, agentData]) => {
                const judgeEval = agentData.judge_evaluation || {};
                const scores = judgeEval.aggregate_scores || {};
                
                Object.entries(scores).forEach(([dimension, scoreObj]) => {
                    const score = scoreObj.score || 0;
                    if (score < 3.5) {
                        lowScoringDimensions.add(dimension);
                    }
                });
            });

            // Define all criteria guidance
            const allCriteriaGuidance = {
                'helpfulness': {
                    title: 'Helpfulness - Addresses user needs and provides actionable solutions',
                    details: 'Evaluates how well the agent identifies user problems and offers practical, implementable solutions.',
                    nextSteps: [
                        '• Review agent prompts to ensure they prioritize solution-oriented responses',
                        '• Add explicit instructions to provide step-by-step guidance',
                        '• Include examples of actionable recommendations in training data',
                        '• Test with diverse use cases to ensure broad applicability',
                        '• Monitor user feedback on solution effectiveness'
                    ]
                },
                'accuracy': {
                    title: 'Accuracy - Correctness of technical information and recommendations',
                    details: 'Measures the factual correctness and technical validity of agent responses.',
                    nextSteps: [
                        '• Validate technical documentation and knowledge base sources',
                        '• Implement fact-checking mechanisms for technical claims',
                        '• Regular updates to reflect latest AWS services and best practices',
                        '• Cross-reference responses with official AWS documentation',
                        '• Establish subject matter expert review processes'
                    ]
                },
                'clarity': {
                    title: 'Clarity - Clear, organized, and easy to understand responses',
                    details: 'Assesses response structure, readability, and logical flow of information.',
                    nextSteps: [
                        '• Use consistent formatting and structure templates',
                        '• Break complex topics into digestible sections',
                        '• Add clear headings and bullet points for organization',
                        '• Avoid technical jargon without explanations',
                        '• Include examples and analogies for complex concepts'
                    ]
                },
                'professionalism': {
                    title: 'Professionalism - Appropriate technical language, tone, and communication style',
                    details: 'Evaluates communication style, technical vocabulary usage, and professional demeanor.',
                    nextSteps: [
                        '• Define and maintain consistent tone guidelines',
                        '• Balance technical precision with accessibility',
                        '• Use appropriate level of formality for enterprise users',
                        '• Ensure respectful and helpful communication style',
                        '• Avoid assumptions about user technical expertise'
                    ]
                },
                'completeness': {
                    title: 'Completeness - Thoroughness in addressing all aspects of the query',
                    details: 'Measures how comprehensively the agent addresses all parts of user questions.',
                    nextSteps: [
                        '• Implement query parsing to identify multiple question components',
                        '• Create checklists for common troubleshooting scenarios',
                        '• Include related considerations and edge cases in responses',
                        '• Provide context and background information when relevant',
                        '• Offer follow-up questions to ensure full problem resolution'
                    ]
                }
            };

            // Add criteria guidance only for low-scoring dimensions
            lowScoringDimensions.forEach(dimension => {
                const criteria = allCriteriaGuidance[dimension];
                if (criteria) {
                    const item = document.createElement('div');
                    item.className = 'recommendation-item criteria-guidance';
                    item.innerHTML = `
                        <div class="recommendation-priority priority-info">📋 Low-Scoring Evaluation Criteria</div>
                        <div class="criteria-title">${criteria.title}</div>
                        <div class="criteria-details">${criteria.details}</div>
                        <div class="criteria-next-steps">
                            <strong>Improvement Actions:</strong>
                            ${criteria.nextSteps.map(step => `<div class="next-step">${step}</div>`).join('')}
                        </div>
                    `;
                    recommendationsContent.appendChild(item);
                }
            });

            // Generate specific recommendations based on results
            Object.entries(evaluationData.detailed_results || {}).forEach(([agentName, agentData]) => {
                const judgeEval = agentData.judge_evaluation || {};
                const overallScore = judgeEval.overall_score || 0;
                const scores = judgeEval.aggregate_scores || {};
                
                if (overallScore < 4.0) {
                    recommendations.push({
                        priority: 'high',
                        text: `${agentName} requires attention - overall score ${overallScore.toFixed(1)}/5.0 is below recommended threshold of 4.0. Focus on the lowest scoring criteria above.`
                    });
                }
                
                Object.entries(scores).forEach(([dimension, scoreObj]) => {
                    const score = scoreObj.score || 0;
                    if (score < 3.5) {
                        recommendations.push({
                            priority: 'medium',
                            text: `${agentName} shows low ${dimension} score (${score.toFixed(1)}/5.0) - review the ${dimension} guidance above for specific improvement actions`
                        });
                    }
                });
            });
            
            // Add general recommendations
            recommendations.push({
                priority: 'low',
                text: 'Regular evaluation runs recommended to track performance trends over time and measure improvement'
            });
            
            recommendations.push({
                priority: 'low',
                text: 'Consider implementing automated alerts for scores below threshold (4.0 overall, 3.5 per dimension)'
            });
            
            recommendations.forEach(rec => {
                const item = document.createElement('div');
                item.className = 'recommendation-item';
                item.innerHTML = `
                    <div class="recommendation-priority priority-${rec.priority}">${rec.priority} Priority</div>
                    <div>${rec.text}</div>
                `;
                recommendationsContent.appendChild(item);
            });
        }

        function showErrorMessage(message) {
            const container = document.querySelector('.container');
            const errorDiv = document.createElement('div');
            errorDiv.className = 'error-message';
            errorDiv.textContent = message;
            container.insertBefore(errorDiv, container.firstChild);
        }
    </script>
</body>
</html>
"""

def load_evaluation_results(results_file: str) -> Dict[str, Any]:
    """Load evaluation results from JSON file"""
    try:
        with open(results_file, 'r', encoding='utf-8') as f:
            return json.load(f)
    except FileNotFoundError:
        raise FileNotFoundError(f"Results file not found: {results_file}")
    except json.JSONDecodeError as e:
        raise ValueError(f"Invalid JSON in results file: {e}")

def filter_data_by_agent(data: Dict[str, Any], agent_name: str) -> Dict[str, Any]:
    """Filter evaluation data to show only specified agent"""
    detailed_results = data.get('detailed_results', {})
    
    if agent_name not in detailed_results:
        # Return empty structure if agent not found
        return {
            'detailed_results': {},
            'evaluation_timestamp': data.get('evaluation_timestamp', ''),
            'summary': {
                'total_agents_evaluated': 0,
                'successful_evaluations': 0,
                'evaluation_success_rate': 0.0
            }
        }
    
    # Create filtered data with only the specified agent
    filtered_data = {
        'detailed_results': {agent_name: detailed_results[agent_name]},
        'evaluation_timestamp': data.get('evaluation_timestamp', ''),
        'summary': {
            'total_agents_evaluated': 1,
            'successful_evaluations': 1 if 'error' not in detailed_results[agent_name] else 0,
            'evaluation_success_rate': 100.0 if 'error' not in detailed_results[agent_name] else 0.0
        }
    }
    
    return filtered_data

def calculate_summary_metrics(data: Dict[str, Any]) -> Dict[str, Any]:
    """Calculate summary metrics from evaluation data"""
    detailed_results = data.get('detailed_results', {})
    
    if not detailed_results:
        return {
            'overall_score': 0.0,
            'success_rate': 0.0,
            'total_tests': 0,
            'avg_response_time': 0.0
        }
    
    # Count individual test cases, not agents
    individual_test_scores = []
    passed_tests = 0
    total_individual_tests = 0
    response_times = []
    
    for agent_data in detailed_results.values():
        judge_eval = agent_data.get('judge_evaluation', {})
        test_results = agent_data.get('workflow', {}).get('test_results', [])
        judge_evaluations = judge_eval.get('judge_evaluations', [])
        
        # Count individual test cases
        for test_result in test_results:
            total_individual_tests += 1
            test_case_id = test_result.get('test_case_id', f'test_{total_individual_tests}')
            
            # Find corresponding judge evaluation for this test case
            test_judge_eval = next((eval for eval in judge_evaluations if eval.get('test_case_id') == test_case_id), None)
            if test_judge_eval:
                test_score = test_judge_eval.get('overall_score', 0)
                individual_test_scores.append(test_score)
                
                if test_score >= 4.0:
                    passed_tests += 1
            
            # Extract response time for this test
            response_time = test_result.get('response_time')
            if response_time:
                response_times.append(response_time)
    
    return {
        'overall_score': sum(individual_test_scores) / len(individual_test_scores) if individual_test_scores else 0.0,
        'success_rate': (passed_tests / total_individual_tests * 100) if total_individual_tests > 0 else 0.0,
        'total_tests': total_individual_tests,
        'avg_response_time': sum(response_times) / len(response_times) if response_times else 0.0
    }

def get_aws_info() -> Dict[str, str]:
    """Get AWS account and region information"""
    try:
        import boto3
        sts = boto3.client('sts')
        response = sts.get_caller_identity()
        account_id = response.get('Account', 'Unknown')
        
        session = boto3.Session()
        region = session.region_name or 'Unknown'
        
        return {
            'account_id': account_id,
            'region': region
        }
    except Exception:
        return {
            'account_id': 'Unknown',
            'region': 'Unknown'
        }

def upload_report_to_s3(local_file_path: str, account_id: str) -> bool:
    """Upload HTML report directly to S3 bucket root"""
    try:
        import boto3
        
        # Get S3 bucket from environment or config
        s3_bucket = os.getenv('S3_RESULTS_BUCKET', '')
        if not s3_bucket:
            logging.warning("No S3_RESULTS_BUCKET configured, skipping S3 upload")
            return False
        
        # Create S3 client
        s3_client = boto3.client('s3')
        
        # Upload directly to bucket root (no folder structure)
        file_name = Path(local_file_path).name
        s3_key = file_name
        
        # Upload file to S3
        s3_client.upload_file(local_file_path, s3_bucket, s3_key)
        
        # Generate S3 URL
        s3_url = f"https://{s3_bucket}.s3.amazonaws.com/{s3_key}"
        
        logging.info(f"HTML report uploaded to S3: {s3_url}")
        print(f"📤 Report uploaded to S3: s3://{s3_bucket}/{s3_key}")
        print(f"🌐 S3 URL: {s3_url}")
        
        return True
        
    except Exception as e:
        logging.warning(f"Failed to upload report to S3: {e}")
        print(f"⚠️  S3 upload failed: {e}")
        return False

def generate_html_report(results_file: str, output_file: str = None, upload_to_s3: bool = True, agent_filter: str = None) -> str:
    """Generate HTML report from evaluation results"""
    
    # Load evaluation results
    data = load_evaluation_results(results_file)
    
    # Filter data by specific agent if requested
    if agent_filter:
        data = filter_data_by_agent(data, agent_filter)
        if not data['detailed_results']:
            raise ValueError(f"Agent '{agent_filter}' not found in evaluation results. Available agents: {list(load_evaluation_results(results_file).get('detailed_results', {}).keys())}")
    
    # Calculate summary metrics
    metrics = calculate_summary_metrics(data)
    
    # Get AWS information
    aws_info = get_aws_info()
    
    # Get timestamp
    timestamp = datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')
    
    # Generate output filename if not provided
    if output_file is None:
        timestamp_str = datetime.now().strftime('%Y%m%d_%H%M%S')
        agent_suffix = f"_{agent_filter}" if agent_filter else ""
        output_file = f'reports/evaluation_score_card{agent_suffix}_{timestamp_str}.html'
    
    # Prepare template replacements
    report_title = f"🎯 AgentCore Evaluation Score Card"
    if agent_filter:
        report_title += f" - {agent_filter}"
    
    replacements = {
        'TIMESTAMP': timestamp,
        'OVERALL_SCORE': f"{metrics['overall_score']:.1f}/5.0",
        'SUCCESS_RATE': f"{metrics['success_rate']:.0f}",
        'TOTAL_TESTS': str(metrics['total_tests']),
        'AVG_RESPONSE_TIME': f"{metrics['avg_response_time']:.1f}",
        'ACCOUNT_ID': aws_info['account_id'],
        'REGION': aws_info['region'],
        'EVALUATION_DATA': json.dumps(data, default=str, indent=2)
    }
    
    # Replace placeholders in template
    html_content = HTML_TEMPLATE
    
    # Update title if filtering by agent
    if agent_filter:
        html_content = html_content.replace('🎯 AgentCore Evaluation Score Card', report_title)
    
    for placeholder, value in replacements.items():
        html_content = html_content.replace('{{' + placeholder + '}}', str(value))
    
    # Ensure output directory exists
    output_path = Path(output_file)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    
    # Write HTML file
    with open(output_path, 'w', encoding='utf-8') as f:
        f.write(html_content)
    
    # Upload to S3 if requested
    if upload_to_s3:
        upload_report_to_s3(str(output_path), aws_info['account_id'])
    
    return str(output_path)

def main():
    """Main function"""
    parser = argparse.ArgumentParser(
        description="Generate HTML score card report from AgentCore evaluation results",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s --results-file evaluation_results.json
  %(prog)s --results-file reports/evaluation_results_20241029.json --output dashboard.html
  %(prog)s --input reports/ --latest  # Use latest results file in directory
        """
    )
    
    parser.add_argument(
        '--results-file',
        type=str,
        help='Path to evaluation results JSON file'
    )
    
    parser.add_argument(
        '--input',
        type=str,
        default='reports',
        help='Directory to search for results files (default: reports)'
    )
    
    parser.add_argument(
        '--latest',
        action='store_true',
        help='Use the latest results file in the input directory'
    )
    
    parser.add_argument(
        '--output',
        type=str,
        help='Output HTML file path (default: auto-generated in reports/)'
    )
    
    parser.add_argument(
        '--agent',
        type=str,
        help='Filter results to show only specified agent (e.g., PerformanceAgent, TroubleshootingAgent)'
    )
    
    parser.add_argument(
        '--debug',
        action='store_true',
        help='Enable debug logging'
    )
    
    parser.add_argument(
        '--no-s3-upload',
        action='store_true',
        help='Skip uploading report to S3'
    )
    
    args = parser.parse_args()
    
    # Setup logging
    level = logging.DEBUG if args.debug else logging.INFO
    logging.basicConfig(
        level=level,
        format='%(asctime)s - %(levelname)s - %(message)s'
    )
    logger = logging.getLogger(__name__)
    
    try:
        # Determine results file
        if args.latest or not args.results_file:
            # Find latest results file
            input_dir = Path(args.input)
            if not input_dir.exists():
                logger.error(f"Input directory does not exist: {input_dir}")
                sys.exit(1)
            
            json_files = list(input_dir.glob('evaluation_results_*.json'))
            if not json_files:
                logger.error(f"No evaluation results files found in {input_dir}")
                sys.exit(1)
            
            # Sort by modification time and get the latest
            results_file = max(json_files, key=lambda p: p.stat().st_mtime)
            logger.info(f"Using latest results file: {results_file}")
        else:
            results_file = args.results_file
            if not Path(results_file).exists():
                logger.error(f"Results file does not exist: {results_file}")
                sys.exit(1)
        
        # Generate HTML report
        logger.info("Generating HTML report...")
        upload_to_s3 = not args.no_s3_upload
        output_path = generate_html_report(str(results_file), args.output, upload_to_s3, args.agent)
        
        logger.info(f"HTML report generated: {output_path}")
        
        
        # Print success message
        print(f"\n🎉 HTML Report Generated Successfully!")
        print(f"📊 Report Location: {output_path}")
        print(f"🌐 Open in browser: file://{os.path.abspath(output_path)}")
        
    except Exception as e:
        logger.error(f"Failed to generate HTML report: {e}")
        if args.debug:
            import traceback
            logger.error(traceback.format_exc())
        sys.exit(1)


if __name__ == "__main__":
    main()
