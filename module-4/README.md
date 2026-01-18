# AgentCore Evaluation Framework

A comprehensive LLM-as-a-Judge evaluation framework for evaluating AgentCore agents using advanced automated assessment techniques with AWS runtime discovery.

## 🎯 Overview

This evaluation framework provides automated, comprehensive assessment of AgentCore agents using LLM-as-a-Judge methodology with Claude Sonnet 4. The framework automatically discovers and evaluates agents deployed in your AWS account:

1. **TroubleshootingAgent** (`a2a_troubleshooting_agent_runtime`) - DNS resolution, connectivity analysis, user consent validation
2. **PerformanceAgent** (`a2a_performance_agent_runtime`) - Network flow monitoring, PCAP analysis, parameter extraction  
3. **CollaboratorAgent** (`a2a_collaborator_agent_runtime`) - A2A communication, agent routing, retry logic

## 🚀 Quick Start (3 Simple Steps)

### Step 1: AWS Prerequisites Setup
```bash
# Navigate to the evaluation framework
cd module-4

# Run automated AWS setup (creates IAM roles, S3 bucket, validates Bedrock access)
./scripts/setup_aws_prerequisites.sh
```

### Step 2: Install Dependencies
```bash
# Create virtual environment (recommended)
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt
```

### Step 3: Run Evaluation
```bash
# Quick evaluation (safety tests + HTML report + auto-open browser)
./scripts/run_evaluation.sh --quick

# OR comprehensive evaluation (all tests + detailed report)
./scripts/run_evaluation.sh --full
```

**That's it!** The evaluation framework will:
- ✅ Automatically discover your AgentCore runtime ARNs from AWS
- ✅ Run comprehensive evaluations using LLM-as-a-Judge
- ✅ Generate interactive HTML reports with charts and analysis
- ✅ Open results in your browser

## 🏗 Architecture

### Core Components

```
AWS Account Discovery → AgentCore Runtime Invocation → LLM Judge Evaluation → HTML Dashboard
        ↓                           ↓                           ↓                    ↓
Runtime ARNs          bedrock-agentcore service          Claude Sonnet 4        Interactive Reports
```

### Evaluation Methodology

- **AWS Runtime Discovery**: Automatically finds agent runtime ARNs in your AWS account
- **Dynamic Configuration**: No hardcoded values - fully configurable via AWS discovery
- **5-Dimensional Scoring**: Helpfulness, Accuracy, Clarity, Professionalism, Completeness  
- **Multi-Layer Tool Detection**: CloudWatch Logs Insights → filter_log_events → content-based fallback
- **Real-Time HTML Reports**: Interactive dashboards with charts, metrics, and recommendations

## 📋 Prerequisites

### AWS Account Requirements
- **AWS Account** with administrative access
- **Amazon Bedrock** access with Claude Sonnet 4 (or Claude 3.5 Sonnet as fallback)
- **AgentCore Agents** deployed with runtime names:
  - `a2a_troubleshooting_agent_runtime`
  - `a2a_performance_agent_runtime`
  - `a2a_collaborator_agent_runtime`

### Local Environment
- **Python 3.8+** (recommended: 3.9+)
- **AWS CLI** configured with credentials
- **Git** (for cloning)

## ⚙️ Automated Setup Details

### What `setup_aws_prerequisites.sh` Does:
1. **Validates AWS CLI** configuration and credentials
2. **Checks Bedrock access** for Claude models
3. **Creates IAM policy** with minimal required permissions:
   - Bedrock model invocation
   - CloudWatch Logs access
   - Agent runtime discovery
   - S3 results storage
4. **Creates IAM role** for evaluation framework
5. **Creates S3 bucket** for storing evaluation results
6. **Generates `.env` file** with configuration
7. **Validates setup** with test operations

### Generated AWS Resources:
- **IAM Policy**: `AgentCoreEvaluationPolicy`
- **IAM Role**: `AgentCoreEvaluationRole`
- **S3 Bucket**: `agentcore-evaluation-results-<timestamp>`
- **.env file**: Environment configuration

## 🎛 Usage Options

### Simple Commands
```bash
# Quick safety evaluation (fastest)
./scripts/run_evaluation.sh --quick

# Complete evaluation suite (comprehensive)
./scripts/run_evaluation.sh --full

# Default evaluation with HTML report
./scripts/run_evaluation.sh

# Safety tests only
./scripts/run_evaluation.sh --safety-only

# Specific agent evaluation
./scripts/run_evaluation.sh --agent TroubleshootingAgent --debug
```

### Advanced Usage
```bash
# Custom output files
./scripts/run_evaluation.sh --output my_results.json --html-output my_dashboard.html

# Generate report from existing results
python scripts/generate_html_report.py --latest --open

# Debug mode with detailed logging
./scripts/run_evaluation.sh --debug --timeout 600
```

## 📊 Understanding Results

### HTML Dashboard Features
- **Executive Summary**: Overall scores, success rates, response times
- **Agent Performance Comparison**: Radar charts comparing all dimensions
- **Individual Agent Cards**: Detailed breakdowns per agent
- **Interactive Results Table**: Filterable test results
- **Automated Recommendations**: AI-generated improvement suggestions

### Quality Score Interpretation
- **5.0**: Exceptional performance, exceeds all requirements
- **4.0-4.9**: Good performance, meets production standards  
- **3.0-3.9**: Acceptable performance, may need minor improvements
- **2.0-2.9**: Below acceptable, requires attention
- **< 2.0**: Critical issues, immediate action required

### Success Benchmarks
| Metric | Minimum Threshold | Target |
|--------|------------------|---------|
| Overall Quality Score | 4.0/5.0 | 4.5/5.0 |
| Success Rate | > 95% | > 98% |
| Safety Compliance | > 4.5/5.0 | 5.0/5.0 |

## 🔧 Configuration

### Dynamic AWS Discovery
The framework automatically discovers your agents from AWS without any manual configuration:

```yaml
# configs/evaluation_config.yaml
agents:
  use_aws_discovery: true  # Automatically discovers runtime ARNs
  target_runtimes:
    - a2a_troubleshooting_agent_runtime
    - a2a_performance_agent_runtime  
    - a2a_collaborator_agent_runtime
```

### LLM Judge Configuration
```yaml
llm_judge:
  model_id: "${BEDROCK_MODEL_ID:-global.anthropic.claude-opus-4-5-20251101-v1:0}"
  fallback_model: "${BEDROCK_FALLBACK_MODEL:-global.anthropic.claude-opus-4-5-20251101-v1:0}"
  temperature: 0.1
  max_tokens: 4000
```

### Environment Variables (Optional)
The `.env` file is automatically generated by the setup script, but you can customize:

```bash
# AWS Configuration
AWS_DEFAULT_REGION=us-east-1
BEDROCK_MODEL_ID=us.anthropic.claude-sonnet-4-20250514-v1:0

# Evaluation Configuration  
EVALUATION_TIMEOUT=300
MAX_CONCURRENT_EVALUATIONS=3
HTML_REPORT_TEMPLATE=dashboard
```

## 🎯 Test Scenarios

### Built-in Safety Tests
- **User Consent Validation**: Ensures agents request permission before making changes
- **Unauthorized Fix Prevention**: Verifies agents don't perform unauthorized actions
- **Data Privacy Compliance**: Checks proper handling of sensitive information

### Performance Tests
- **Response Time Analysis**: Measures agent response latency
- **Tool Detection Accuracy**: Validates correct tool usage identification
- **Error Handling**: Tests graceful failure scenarios

### Custom Test Scenarios
Add custom scenarios in `configs/test_scenarios/agent_test_scenarios.py`:

```python
custom_scenario = TestScenario(
    id="custom_connectivity_test",
    agent_type="TroubleshootingAgent",
    query="Diagnose intermittent DNS resolution issues for internal services",
    category="connectivity",
    expected_tools=["dns-resolve", "network-trace"],
    expected_behavior="Should analyze DNS configuration and provide specific recommendations",
    validation_criteria={"requires_user_consent": True},
    description="Custom connectivity troubleshooting scenario"
)
```

## 🔍 Advanced Features

### AWS Runtime Discovery
The framework uses multiple discovery methods:
1. **Bedrock Agent API**: Primary method for discovering agent runtimes
2. **CloudFormation**: Searches stack resources for AgentCore deployments
3. **Lambda Functions**: Examines function environment variables
4. **IAM Policies**: Analyzes policy attachments for agent references

### Multi-Layer Tool Detection
1. **CloudWatch Logs Insights**: Query-based tool detection
2. **Log Event Filtering**: Direct log analysis
3. **Content-Based Detection**: Fallback text pattern matching
4. **Session Correlation**: Links tool usage to specific evaluation sessions

### Performance Monitoring
- **Real-time Metrics**: Response times, success rates, error rates
- **Historical Trending**: Track performance over time
- **Automated Alerting**: Integration-ready for monitoring systems
- **Detailed Diagnostics**: Debug information for failed evaluations

## 🔒 Security & Compliance

### IAM Permissions (Principle of Least Privilege)
- **Bedrock**: Model invocation only for Claude models
- **CloudWatch**: Read-only access to AgentCore log groups
- **S3**: Limited to evaluation results bucket
- **Runtime Discovery**: Read-only access for agent discovery

### Data Protection
- **Encryption**: All data encrypted in transit and at rest
- **Access Controls**: IAM-based access with role assumptions
- **Data Retention**: Configurable retention policies for results
- **Privacy**: No sensitive data stored in evaluation results

## 🚨 Troubleshooting

### Common Issues & Solutions

#### 1. "No agents discovered from AWS account"
```bash
# Check if your agents are deployed with correct names
aws bedrock-agent list-agents --region us-east-1

# Verify agent runtime names match expected patterns:
# - a2a_troubleshooting_agent_runtime
# - a2a_performance_agent_runtime  
# - a2a_collaborator_agent_runtime
```

#### 2. "AWS discovery failed"
```bash
# Check AWS credentials
aws sts get-caller-identity

# Verify IAM permissions
aws iam get-role --role-name AgentCoreEvaluationRole

# Re-run setup if needed
./scripts/setup_aws_prerequisites.sh
```

#### 3. "Bedrock model access denied"
```bash
# Check available models
aws bedrock list-foundation-models --region us-east-1

# Request model access in AWS Console:
# Bedrock > Model Access > Request Access
```

#### 4. "Evaluation timeout"
```bash
# Increase timeout for complex evaluations
./scripts/run_evaluation.sh --timeout 600 --debug
```

### Debug Mode
```bash
# Enable detailed logging
./scripts/run_evaluation.sh --debug

# Check logs
tail -f evaluation_*.log
```

## 📈 Monitoring & Integration

### CloudWatch Integration
The framework can publish custom metrics to CloudWatch:

```python
# Custom metrics publishing (optional)
cloudwatch.put_metric_data(
    Namespace='AgentCore/Evaluation',
    MetricData=[
        {
            'MetricName': 'OverallScore',
            'Value': overall_score,
            'Unit': 'Count'
        }
    ]
)
```

### CI/CD Integration
```yaml
# .github/workflows/agent-evaluation.yml
name: AgentCore Evaluation
on:
  schedule:
    - cron: '0 6 * * *'  # Daily at 6 AM UTC
  workflow_dispatch:

jobs:
  evaluate:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v3
      - uses: aws-actions/configure-aws-credentials@v2
        with:
          aws-access-key-id: ${{ secrets.AWS_ACCESS_KEY_ID }}
          aws-secret-access-key: ${{ secrets.AWS_SECRET_ACCESS_KEY }}
          aws-region: us-east-1
      - name: Run Evaluation
        run: |
          cd module-4
          ./scripts/run_evaluation.sh --quick
```

## 🤝 Contributing

### Development Setup
```bash
# Clone and setup development environment
git clone <repository>
cd module-4

# Install development dependencies
pip install -r requirements.txt
pip install -e .

# Run tests
python -m pytest tests/ -v

# Format code
black src/ scripts/
flake8 src/ scripts/
```

### Adding New Evaluation Dimensions
1. Update evaluation rubrics in `configs/test_scenarios/agent_test_scenarios.py`
2. Modify LLM judge prompts in `src/evaluation/agent_evaluation_pipeline.py`
3. Add new chart types in HTML report template
4. Update documentation

## 📚 File Structure

```
module-4/
├── README.md                              # This file
├── requirements.txt                       # Python dependencies
├── .env                                   # Auto-generated environment config
├── scripts/
│   ├── setup_aws_prerequisites.sh        # Automated AWS setup
│   ├── run_evaluation.sh                 # Main evaluation runner
│   ├── run_evaluation.py                 # Python evaluation script
│   └── generate_html_report.py           # HTML report generator
├── src/evaluation/
│   ├── agent_evaluation_pipeline.py      # Main evaluation framework
│   ├── aws_runtime_discovery.py          # AWS agent discovery
│   ├── config_loader.py                  # Dynamic configuration
│   └── agentcore_client.py               # AgentCore service client
├── configs/
│   ├── evaluation_config.yaml            # Main configuration
│   └── test_scenarios/
│       └── agent_test_scenarios.py       # Test scenarios & rubrics
├── reports/                               # Generated reports
│   ├── evaluation_results_*.json         # JSON results
│   └── evaluation_dashboard_*.html       # HTML dashboards
└── tests/                                 # Unit tests
```

## 🎉 Success Indicators

After successful setup and execution, you should see:

1. **✅ AWS Resources Created**: IAM role, S3 bucket, policies configured
2. **✅ Agents Discovered**: Runtime ARNs automatically found in your AWS account
3. **✅ Evaluations Complete**: All agents evaluated with quality scores
4. **✅ HTML Report Generated**: Interactive dashboard created and opened
5. **✅ Results Stored**: JSON and HTML reports saved to `reports/` directory

### Example Success Output:
```
🎯 AgentCore Evaluation Framework
===================================
✅ AWS CLI configured for account: 123456789012
✅ Claude Sonnet 4 model access available
✅ Dependencies installed successfully
✅ Evaluation completed successfully
✅ HTML report generated successfully
🎉 HTML Report Generated Successfully!
📊 Report Location: reports/evaluation_dashboard_20241029_130445.html
🌐 Open in browser: file:///path/to/reports/evaluation_dashboard_20241029_130445.html
```

## 📞 Support

### Quick Reference Commands
```bash
# Complete setup and evaluation (one command)
./scripts/setup_aws_prerequisites.sh && ./scripts/run_evaluation.sh --quick

# Generate report from existing results
python scripts/generate_html_report.py --latest --open

# Debug failed evaluation
./scripts/run_evaluation.sh --debug --agent TroubleshootingAgent

# View help
./scripts/run_evaluation.sh --help
```

### Get Help
- **Setup Issues**: Run `./scripts/setup_aws_prerequisites.sh --help`
- **Evaluation Issues**: Run `./scripts/run_evaluation.sh --help`
- **Report Issues**: Run `python scripts/generate_html_report.py --help`

---

## 🚀 Ready to Get Started?

1. **Setup AWS**: `./scripts/setup_aws_prerequisites.sh`
2. **Install Dependencies**: `pip install -r requirements.txt` 
3. **Run Evaluation**: `./scripts/run_evaluation.sh --quick`

**Your AgentCore agents will be automatically discovered and evaluated within minutes!** 🎯
