#!/bin/bash
# Script to convert Mermaid diagrams to PNG images
# Requires: npm install -g @mermaid-js/mermaid-cli

set -e

echo "Converting Mermaid diagrams to PNG images..."

# Check if mmdc is available
if ! command -v mmdc &> /dev/null; then
    echo "Error: mmdc (Mermaid CLI) is not installed."
    echo "Please install it with: npm install -g @mermaid-js/mermaid-cli"
    exit 1
fi


echo "Converting 01_Performance_Tools_Flow_Diagram.mmd to 01_Performance_Tools_Flow_Diagram.png..."
mmdc -i "/Users/aksareen/Documents/code.aws.dev/netops-agentic-ai/agentcore-performance-agent/images/flow_diagrams/01_Performance_Tools_Flow_Diagram.mmd" -o "/Users/aksareen/Documents/code.aws.dev/netops-agentic-ai/agentcore-performance-agent/images/flow_diagrams/01_Performance_Tools_Flow_Diagram.png" -t dark -b transparent

echo "Converting 02_1_PerformanceAnalyzer__init___Flow.mmd to 02_1_PerformanceAnalyzer__init___Flow.png..."
mmdc -i "/Users/aksareen/Documents/code.aws.dev/netops-agentic-ai/agentcore-performance-agent/images/flow_diagrams/02_1_PerformanceAnalyzer__init___Flow.mmd" -o "/Users/aksareen/Documents/code.aws.dev/netops-agentic-ai/agentcore-performance-agent/images/flow_diagrams/02_1_PerformanceAnalyzer__init___Flow.png" -t dark -b transparent

echo "Converting 03_2_analyze_vpc_flow_metrics_Flow.mmd to 03_2_analyze_vpc_flow_metrics_Flow.png..."
mmdc -i "/Users/aksareen/Documents/code.aws.dev/netops-agentic-ai/agentcore-performance-agent/images/flow_diagrams/03_2_analyze_vpc_flow_metrics_Flow.mmd" -o "/Users/aksareen/Documents/code.aws.dev/netops-agentic-ai/agentcore-performance-agent/images/flow_diagrams/03_2_analyze_vpc_flow_metrics_Flow.png" -t dark -b transparent

echo "Converting 04_3_create_subnet_flow_monitor_Flow.mmd to 04_3_create_subnet_flow_monitor_Flow.png..."
mmdc -i "/Users/aksareen/Documents/code.aws.dev/netops-agentic-ai/agentcore-performance-agent/images/flow_diagrams/04_3_create_subnet_flow_monitor_Flow.mmd" -o "/Users/aksareen/Documents/code.aws.dev/netops-agentic-ai/agentcore-performance-agent/images/flow_diagrams/04_3_create_subnet_flow_monitor_Flow.png" -t dark -b transparent

echo "Converting 05_4_setup_traffic_mirroring_Flow.mmd to 05_4_setup_traffic_mirroring_Flow.png..."
mmdc -i "/Users/aksareen/Documents/code.aws.dev/netops-agentic-ai/agentcore-performance-agent/images/flow_diagrams/05_4_setup_traffic_mirroring_Flow.mmd" -o "/Users/aksareen/Documents/code.aws.dev/netops-agentic-ai/agentcore-performance-agent/images/flow_diagrams/05_4_setup_traffic_mirroring_Flow.png" -t dark -b transparent

echo "Converting 06_5__setup_packet_capture_on_target_Flow.mmd to 06_5__setup_packet_capture_on_target_Flow.png..."
mmdc -i "/Users/aksareen/Documents/code.aws.dev/netops-agentic-ai/agentcore-performance-agent/images/flow_diagrams/06_5__setup_packet_capture_on_target_Flow.mmd" -o "/Users/aksareen/Documents/code.aws.dev/netops-agentic-ai/agentcore-performance-agent/images/flow_diagrams/06_5__setup_packet_capture_on_target_Flow.png" -t dark -b transparent

echo "Converting 07_6_analyze_tcp_performance_Flow.mmd to 07_6_analyze_tcp_performance_Flow.png..."
mmdc -i "/Users/aksareen/Documents/code.aws.dev/netops-agentic-ai/agentcore-performance-agent/images/flow_diagrams/07_6_analyze_tcp_performance_Flow.mmd" -o "/Users/aksareen/Documents/code.aws.dev/netops-agentic-ai/agentcore-performance-agent/images/flow_diagrams/07_6_analyze_tcp_performance_Flow.png" -t dark -b transparent

echo "Converting 08_7_analyze_captured_traffic_data_Flow.mmd to 08_7_analyze_captured_traffic_data_Flow.png..."
mmdc -i "/Users/aksareen/Documents/code.aws.dev/netops-agentic-ai/agentcore-performance-agent/images/flow_diagrams/08_7_analyze_captured_traffic_data_Flow.mmd" -o "/Users/aksareen/Documents/code.aws.dev/netops-agentic-ai/agentcore-performance-agent/images/flow_diagrams/08_7_analyze_captured_traffic_data_Flow.png" -t dark -b transparent

echo "Converting 09_8__generate_traffic_analysis_commands_Flow.mmd to 09_8__generate_traffic_analysis_commands_Flow.png..."
mmdc -i "/Users/aksareen/Documents/code.aws.dev/netops-agentic-ai/agentcore-performance-agent/images/flow_diagrams/09_8__generate_traffic_analysis_commands_Flow.mmd" -o "/Users/aksareen/Documents/code.aws.dev/netops-agentic-ai/agentcore-performance-agent/images/flow_diagrams/09_8__generate_traffic_analysis_commands_Flow.png" -t dark -b transparent

echo "Converting 10_9_Public_Async_Function_Wrappers_Flow.mmd to 10_9_Public_Async_Function_Wrappers_Flow.png..."
mmdc -i "/Users/aksareen/Documents/code.aws.dev/netops-agentic-ai/agentcore-performance-agent/images/flow_diagrams/10_9_Public_Async_Function_Wrappers_Flow.mmd" -o "/Users/aksareen/Documents/code.aws.dev/netops-agentic-ai/agentcore-performance-agent/images/flow_diagrams/10_9_Public_Async_Function_Wrappers_Flow.png" -t dark -b transparent

echo "Converting 11_10_install_network_flow_monitor_agent_Special_Flow.mmd to 11_10_install_network_flow_monitor_agent_Special_Flow.png..."
mmdc -i "/Users/aksareen/Documents/code.aws.dev/netops-agentic-ai/agentcore-performance-agent/images/flow_diagrams/11_10_install_network_flow_monitor_agent_Special_Flow.mmd" -o "/Users/aksareen/Documents/code.aws.dev/netops-agentic-ai/agentcore-performance-agent/images/flow_diagrams/11_10_install_network_flow_monitor_agent_Special_Flow.png" -t dark -b transparent

echo "Converting 12_diagram_12.mmd to 12_diagram_12.png..."
mmdc -i "/Users/aksareen/Documents/code.aws.dev/netops-agentic-ai/agentcore-performance-agent/images/flow_diagrams/12_diagram_12.mmd" -o "/Users/aksareen/Documents/code.aws.dev/netops-agentic-ai/agentcore-performance-agent/images/flow_diagrams/12_diagram_12.png" -t dark -b transparent

echo "Converting 13_diagram_13.mmd to 13_diagram_13.png..."
mmdc -i "/Users/aksareen/Documents/code.aws.dev/netops-agentic-ai/agentcore-performance-agent/images/flow_diagrams/13_diagram_13.mmd" -o "/Users/aksareen/Documents/code.aws.dev/netops-agentic-ai/agentcore-performance-agent/images/flow_diagrams/13_diagram_13.png" -t dark -b transparent

echo "Converting 14_diagram_14.mmd to 14_diagram_14.png..."
mmdc -i "/Users/aksareen/Documents/code.aws.dev/netops-agentic-ai/agentcore-performance-agent/images/flow_diagrams/14_diagram_14.mmd" -o "/Users/aksareen/Documents/code.aws.dev/netops-agentic-ai/agentcore-performance-agent/images/flow_diagrams/14_diagram_14.png" -t dark -b transparent

echo "All diagrams converted successfully!"
echo "Images saved in: /Users/aksareen/Documents/code.aws.dev/netops-agentic-ai/agentcore-performance-agent/images/flow_diagrams"
