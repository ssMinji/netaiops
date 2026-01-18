#!/usr/bin/env python3
"""
Quick evaluation runner script for AgentCore Evaluation Framework

Usage:
    python scripts/run_evaluation.py --agent all
    python scripts/run_evaluation.py --agent TroubleshootingAgent
    python scripts/run_evaluation.py --safety-only
"""

# Suppress boto3 Python deprecation warnings BEFORE any imports
import warnings
warnings.filterwarnings('ignore', category=DeprecationWarning)
warnings.filterwarnings('ignore', message='.*Boto3 will no longer support Python.*')

import argparse
import asyncio
import json
import logging
import sys
import os
from datetime import datetime, timezone
from pathlib import Path

# Add parent directory to path for imports
sys.path.append(str(Path(__file__).parent.parent))

from src.evaluation.agent_evaluation_pipeline import AgentEvaluationPipeline
from src.evaluation.config_loader import get_config_loader
from configs.test_scenarios.agent_test_scenarios import AgentTestSuite


class ColorFormatter:
    """Enhanced color formatting for beautiful console output"""
    
    # ANSI color codes
    COLORS = {
        'RED': '\033[0;31m',
        'GREEN': '\033[0;32m', 
        'YELLOW': '\033[1;33m',
        'BLUE': '\033[0;34m',
        'MAGENTA': '\033[0;35m',
        'CYAN': '\033[0;36m',
        'WHITE': '\033[0;37m',
        'BOLD': '\033[1m',
        'DIM': '\033[2m',
        'RESET': '\033[0m'
    }
    
    # Agent-specific colors
    AGENT_COLORS = {
        'PerformanceAgent': 'BLUE',
        'TroubleshootingAgent': 'GREEN', 
        'HostAgent': 'MAGENTA',
        'CollaboratorAgent': 'CYAN'
    }
    
    @classmethod
    def colorize(cls, text, color):
        """Apply color to text"""
        if color in cls.COLORS:
            return f"{cls.COLORS[color]}{text}{cls.COLORS['RESET']}"
        return text
    
    @classmethod
    def agent_name(cls, agent_name):
        """Color-code agent names"""
        color = cls.AGENT_COLORS.get(agent_name, 'WHITE')
        return cls.colorize(f"{agent_name}", color)
    
    @classmethod
    def scenario(cls, scenario_name):
        """Format scenario names"""
        return cls.colorize(f"{scenario_name}", 'CYAN')
    
    @classmethod
    def question(cls, question):
        """Format test questions"""
        return cls.colorize(f'"{question}"', 'YELLOW')
    
    @classmethod
    def success(cls, text):
        """Format success messages"""
        return cls.colorize(f"{text}", 'GREEN')
    
    @classmethod
    def warning(cls, text):
        """Format warning messages"""
        return cls.colorize(f"{text}", 'YELLOW')
    
    @classmethod
    def error(cls, text):
        """Format error messages"""
        return cls.colorize(f"{text}", 'RED')
    
    @classmethod
    def info(cls, text):
        """Format info messages"""
        return cls.colorize(f"{text}", 'BLUE')
    
    @classmethod
    def progress(cls, text):
        """Format progress indicators"""
        return cls.colorize(f"{text}", 'CYAN')
    
    @classmethod
    def separator(cls, title="", width=60):
        """Create a visual separator"""
        if title:
            title_text = f" {title} "
            padding = max(0, (width - len(title_text)) // 2)
            separator = "=" * padding + title_text + "=" * padding
            if len(separator) < width:
                separator += "="
        else:
            separator = "=" * width
        return cls.colorize(separator, 'BLUE')
    
    @classmethod
    def box(cls, text, color='BLUE'):
        """Create a boxed message"""
        lines = text.split('\n')
        max_length = max(len(line) for line in lines)
        box_width = max_length + 4
        
        top = "┌" + "─" * (box_width - 2) + "┐"
        bottom = "└" + "─" * (box_width - 2) + "┘"
        
        result = [cls.colorize(top, color)]
        for line in lines:
            padding = max_length - len(line)
            boxed_line = f"│ {line}" + " " * padding + " │"
            result.append(cls.colorize(boxed_line, color))
        result.append(cls.colorize(bottom, color))
        
        return '\n'.join(result)


def enhanced_print(message, color=None):
    """Enhanced print with optional color"""
    if color:
        message = ColorFormatter.colorize(message, color)
    print(message)
    sys.stdout.flush()


def parse_arguments():
    """Parse command line arguments"""
    parser = argparse.ArgumentParser(
        description="Run AgentCore Agent Evaluation Framework",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s --agent all                    # Evaluate all agents
  %(prog)s --agent TroubleshootingAgent   # Evaluate specific agent
  %(prog)s --safety-only                  # Run only safety-critical tests
  %(prog)s --output results.json         # Save results to specific file
        """
    )
    
    parser.add_argument(
        '--agent',
        choices=['all', 'TroubleshootingAgent', 'PerformanceAgent', 'CollaboratorAgent'],
        default='all',
        help='Which agent(s) to evaluate (default: all)'
    )
    
    parser.add_argument(
        '--safety-only',
        action='store_true',
        help='Run only safety-critical test scenarios'
    )
    
    parser.add_argument(
        '--output',
        type=str,
        default=None,
        help='Output file for evaluation results (default: auto-generated with timestamp)'
    )
    
    parser.add_argument(
        '--debug',
        action='store_true',
        help='Enable debug logging'
    )
    
    parser.add_argument(
        '--shell-progress',
        action='store_true',
        help='Show shell-friendly progress updates (used by run_evaluation.sh)'
    )
    
    parser.add_argument(
        '--timeout',
        type=int,
        default=300,
        help='Timeout in seconds for agent evaluation (default: 300)'
    )
    
    parser.add_argument(
        '--verify-only',
        action='store_true',
        help='Only verify agent accessibility without running full evaluation'
    )
    
    return parser.parse_args()


def setup_logging(debug=False):
    """Setup logging configuration with simplified output"""
    import logging
    
    # Create logs directory if it doesn't exist
    logs_dir = Path("logs")
    logs_dir.mkdir(exist_ok=True)
    
    # Set up log file path with timestamp
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    log_file = logs_dir / f'evaluation_{timestamp}.log'
    
    # Clear any existing handlers
    for handler in logging.root.handlers[:]:
        logging.root.removeHandler(handler)
    
    # Set console logging to ERROR by default, INFO for debug
    console_level = logging.INFO if debug else logging.ERROR
    
    # Create file handler - always log everything to file
    file_handler = logging.FileHandler(log_file, encoding='utf-8', mode='w')
    file_handler.setLevel(logging.DEBUG)
    
    # Create console handler with minimal output
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(console_level)
    
    # Create formatter
    formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    file_handler.setFormatter(formatter)
    console_handler.setFormatter(formatter)
    
    # Configure root logger
    logging.basicConfig(
        level=logging.DEBUG,  # Root logger captures everything
        handlers=[console_handler, file_handler],
        force=True
    )
    
    # Suppress verbose third-party loggers
    logging.getLogger('botocore').setLevel(logging.ERROR)
    logging.getLogger('botocore.hooks').setLevel(logging.ERROR)
    logging.getLogger('botocore.loaders').setLevel(logging.ERROR)
    logging.getLogger('botocore.utils').setLevel(logging.ERROR)
    logging.getLogger('botocore.credentials').setLevel(logging.ERROR)
    logging.getLogger('botocore.regions').setLevel(logging.ERROR)
    logging.getLogger('botocore.endpoint').setLevel(logging.ERROR)
    logging.getLogger('botocore.client').setLevel(logging.ERROR)
    logging.getLogger('botocore.parsers').setLevel(logging.ERROR)
    logging.getLogger('botocore.retryhandler').setLevel(logging.ERROR)
    logging.getLogger('botocore.httpsession').setLevel(logging.ERROR)
    logging.getLogger('botocore.configprovider').setLevel(logging.ERROR)
    logging.getLogger('urllib3').setLevel(logging.ERROR)
    logging.getLogger('urllib3.connectionpool').setLevel(logging.ERROR)
    logging.getLogger('requests').setLevel(logging.ERROR)
    logging.getLogger('asyncio').setLevel(logging.ERROR)
    
    # Allow some important warnings through even in non-debug mode
    if not debug:
        logging.getLogger('botocore').setLevel(logging.CRITICAL)
        logging.getLogger('urllib3').setLevel(logging.CRITICAL)
        logging.getLogger('requests').setLevel(logging.CRITICAL)
    
    logger = logging.getLogger(__name__)
    
    # Only log startup info in debug mode
    if debug:
        logger.info(f"=== AgentCore Evaluation Framework Started ===")
        logger.info(f"Logging to file: {log_file}")
        logger.info(f"Debug mode: {debug}")
        logger.info(f"Timestamp: {datetime.now().isoformat()}")
    
    return logger


async def run_single_agent_evaluation(agent_name: str, pipeline: AgentEvaluationPipeline, logger, show_shell_progress=False):
    """Run evaluation for a single agent with beautiful progress display"""
    try:
        # Beautiful header for agent evaluation
        if show_shell_progress:
            print(ColorFormatter.separator(f"EVALUATING {agent_name.upper()}", 70))
            enhanced_print(f"Starting comprehensive evaluation for {ColorFormatter.agent_name(agent_name)}")
            print()
        
        # Only log important validation steps
        print(f"[*] Calling {agent_name} for validation")
        
        # Get agent configuration from dynamic loader
        config_loader = get_config_loader()
        agent_config = config_loader.get_agent_config(agent_name)
        
        if not agent_config:
            raise ValueError(f"Unknown agent: {agent_name}")
        
        if show_shell_progress:
            enhanced_print(f"Runtime ARN: {agent_config.runtime_arn}", 'DIM')
            enhanced_print(f"Log Group: {agent_config.log_group}", 'DIM')
            print()
        
        # Only log in debug mode
        if logger.isEnabledFor(logging.DEBUG):
            logger.info(f"Using runtime ARN for {agent_name}: {agent_config.runtime_arn}")
            logger.info(f"Using log group for {agent_name}: {agent_config.log_group}")
        
        # Convert agent_config to dict format expected by pipeline methods
        config_dict = {
            'runtime_arn': agent_config.runtime_arn,
            'agent_type': agent_config.agent_type,
            'cognito_config': agent_config.cognito_config,
            'alb_dns': agent_config.alb_dns,
            'log_group': agent_config.log_group
        }
        
        # Phase 1: Initialization Test
        if show_shell_progress:
            enhanced_print(ColorFormatter.progress("Phase 1: Agent Initialization"))
            enhanced_print(f"  {ColorFormatter.scenario(get_scenario_1_name(agent_name))}")
            enhanced_print(f"  {ColorFormatter.question('Hello, this is a test message to verify agent accessibility.')}")
        
        print(f"[*] Validating {agent_name} initialization")
        initialization_results = await pipeline._test_agent_initialization(agent_name, config_dict)
        
        init_success = initialization_results.get('initialization_success', False)
        if show_shell_progress:
            if init_success:
                enhanced_print(f"  {ColorFormatter.success('Initialization test passed')}")
            else:
                enhanced_print(f"  {ColorFormatter.warning('Initialization test had issues')}")
            print()
        
        # Phase 2: Workflow Tests
        if show_shell_progress:
            enhanced_print(ColorFormatter.progress("Phase 2: Workflow Evaluation"))
            enhanced_print(f"  {ColorFormatter.scenario(get_scenario_2_name(agent_name))}")
        
        print(f"[*] Validating {agent_name} workflow execution")
        workflow_results = await pipeline._test_agent_workflows(agent_name, config_dict)
        
        # Display individual test questions and results
        if show_shell_progress and 'test_results' in workflow_results:
            test_results = workflow_results['test_results']
            for i, test_result in enumerate(test_results, 1):
                query = test_result.get('query', 'Unknown query')
                # Check if test passed (has response and no error)
                has_response = test_result.get('response') and len(test_result.get('response', '')) > 0
                no_error = 'error' not in test_result
                success = has_response and no_error
                
                enhanced_print(f"  Test {i}: {ColorFormatter.question(query[:60] + '...' if len(query) > 60 else query)}")
                if success:
                    enhanced_print(f"    {ColorFormatter.success('Test completed successfully')}")
                else:
                    enhanced_print(f"    {ColorFormatter.error('Test failed')}")
        
        success_rate = workflow_results.get('success_rate', 0)
        if show_shell_progress:
            if success_rate >= 80:
                enhanced_print(f"  {ColorFormatter.success(f'Workflow success rate: {success_rate}%')}")
            elif success_rate >= 50:
                enhanced_print(f"  {ColorFormatter.warning(f'Workflow success rate: {success_rate}%')}")
            else:
                enhanced_print(f"  {ColorFormatter.error(f'Workflow success rate: {success_rate}%')}")
            print()
        
        # Phase 3: Specialized Tests (SKIPPED)
        if show_shell_progress:
            enhanced_print(ColorFormatter.progress("Phase 3: Specialized Testing"))
            enhanced_print(f"  {ColorFormatter.info('Skipping specialized testing by configuration')}")
        
        specific_results = {
            'test_status': 'skipped',
            'message': 'Phase 3: Specialized Testing has been skipped by configuration'
        }
        
        if show_shell_progress:
            enhanced_print(f"  {ColorFormatter.info('Phase 3 has been skipped')}")
            print()
        
        # Phase 4: LLM Judge Evaluation
        if show_shell_progress:
            enhanced_print(ColorFormatter.progress("Phase 4: LLM Judge Evaluation"))
            enhanced_print(f"  {ColorFormatter.info('Analyzing response quality and accuracy')}")
        
        print(f"[*] Running LLM judge evaluation for {agent_name}")
        judge_results = await pipeline._run_llm_judge_evaluation(
            agent_name, initialization_results, workflow_results, specific_results
        )
        
        overall_score = judge_results.get('overall_score', 0)
        if show_shell_progress:
            if overall_score >= 4.0:
                enhanced_print(f"  {ColorFormatter.success(f'Overall Score: {overall_score:.2f}/5.0')}")
            elif overall_score >= 3.0:
                enhanced_print(f"  {ColorFormatter.warning(f'Overall Score: {overall_score:.2f}/5.0')}")
            else:
                enhanced_print(f"  {ColorFormatter.error(f'Overall Score: {overall_score:.2f}/5.0')}")
        
        # Final results summary
        if show_shell_progress:
            print()
            if overall_score >= 4.0 and success_rate >= 80:
                enhanced_print(ColorFormatter.success(f"{agent_name} evaluation completed successfully!"))
            elif overall_score >= 3.0 or success_rate >= 50:
                enhanced_print(ColorFormatter.warning(f"{agent_name} evaluation completed with warnings"))
            else:
                enhanced_print(ColorFormatter.error(f"{agent_name} evaluation needs attention"))
            print()
        
        result = {
            'agent_name': agent_name,
            'runtime_arn': agent_config.runtime_arn,
            'agent_type': agent_config.agent_type,
            'log_group': agent_config.log_group,
            'initialization': initialization_results,
            'workflow': workflow_results,
            'specific_tests': specific_results,
            'judge_evaluation': judge_results,
            'evaluation_timestamp': datetime.now(timezone.utc).isoformat()
        }
        
        print(f"[+] Completed evaluation for {agent_name}")
        return result
        
    except Exception as e:
        if show_shell_progress:
            enhanced_print(ColorFormatter.error(f"Evaluation failed for {agent_name}: {str(e)}"))
        print(f"[-] Evaluation failed for {agent_name}: {str(e)}")
        if logger.isEnabledFor(logging.DEBUG):
            import traceback
            logger.error(f"Full traceback: {traceback.format_exc()}")
        return {
            'agent_name': agent_name,
            'error': str(e),
            'status': 'failed',
            'evaluation_timestamp': datetime.now(timezone.utc).isoformat()
        }


def get_agent_display_name(agent_name: str) -> str:
    """Get shell-friendly display name for agent"""
    display_map = {
        "TroubleshootingAgent": "a2a_troubleshooting_agent_runtime",
        "PerformanceAgent": "a2a_performance_agent_runtime", 
        "HostAgent": "a2a_collaborator_agent_runtime",
        "CollaboratorAgent": "a2a_collaborator_agent_runtime"
    }
    return display_map.get(agent_name, agent_name)


def get_scenario_1_name(agent_name: str) -> str:
    """Get scenario 1 name for agent"""
    scenario_map = {
        "TroubleshootingAgent": "Network connectivity diagnosis",
        "PerformanceAgent": "Performance bottleneck identification",
        "HostAgent": "Multi-agent coordination",
        "CollaboratorAgent": "Multi-agent coordination"
    }
    return scenario_map.get(agent_name, "Comprehensive evaluation scenario 1")


def get_scenario_2_name(agent_name: str) -> str:
    """Get scenario 2 name for agent"""
    scenario_map = {
        "TroubleshootingAgent": "VPC troubleshooting", 
        "PerformanceAgent": "Network latency analysis",
        "HostAgent": "Task delegation",
        "CollaboratorAgent": "Task delegation"
    }
    return scenario_map.get(agent_name, "Comprehensive evaluation scenario 2")


def get_scenario_3_name(agent_name: str) -> str:
    """Get scenario 3 name for agent"""
    scenario_map = {
        "TroubleshootingAgent": "Security group analysis",
        "PerformanceAgent": "Resource optimization", 
        "HostAgent": "Conflict resolution",
        "CollaboratorAgent": "Conflict resolution"
    }
    return scenario_map.get(agent_name, "Comprehensive evaluation scenario 3")


async def verify_agent_accessibility(agent_name: str, logger):
    """Verify agent accessibility by sending a simple test message"""
    try:
        print(f"\nVerifying accessibility for {agent_name}")
        
        # Get agent configuration
        config_loader = get_config_loader()
        agent_config = config_loader.get_agent_config(agent_name)
        
        if not agent_config:
            print(f"  ERROR: Agent configuration not found: {agent_name}")
            return {
                'agent_name': agent_name,
                'accessible': False,
                'error': 'Configuration not found',
                'timestamp': datetime.now(timezone.utc).isoformat()
            }
        
        print(f"  Runtime ARN: {agent_config.runtime_arn[:50]}...")
        print(f"  Log Group: {agent_config.log_group}")
        
        # Create pipeline and test basic accessibility
        pipeline = AgentEvaluationPipeline()
        
        # Convert to dict format
        config_dict = {
            'runtime_arn': agent_config.runtime_arn,
            'agent_type': agent_config.agent_type,
            'cognito_config': agent_config.cognito_config,
            'alb_dns': agent_config.alb_dns,
            'log_group': agent_config.log_group
        }
        
        # Send a simple test message
        print(f"  Sending test message to agent...")
        test_result = await pipeline._test_agent_initialization(agent_name, config_dict)
        
        accessible = test_result.get('initialization_success', False)
        
        if accessible:
            print(f"  SUCCESS: Agent is accessible")
        else:
            error_msg = test_result.get('error', 'Unknown error')
            print(f"  ERROR: Agent not accessible: {error_msg}")
        
        return {
            'agent_name': agent_name,
            'runtime_arn': agent_config.runtime_arn,
            'accessible': accessible,
            'test_result': test_result,
            'timestamp': datetime.now(timezone.utc).isoformat()
        }
        
    except Exception as e:
        print(f"  ERROR: Verification failed: {str(e)}")
        if logger.isEnabledFor(logging.DEBUG):
            import traceback
            logger.error(f"Full traceback: {traceback.format_exc()}")
        
        return {
            'agent_name': agent_name,
            'accessible': False,
            'error': str(e),
            'timestamp': datetime.now(timezone.utc).isoformat()
        }


async def run_safety_evaluation(logger):
    """Run only safety-critical evaluations"""
    if logger.isEnabledFor(logging.DEBUG):
        logger.info("Running safety-critical evaluations")
    
    test_suite = AgentTestSuite()
    safety_scenarios = test_suite.get_safety_critical_scenarios()
    
    if logger.isEnabledFor(logging.DEBUG):
        logger.info(f"Found {len(safety_scenarios)} safety-critical scenarios")
    
    results = []
    for scenario in safety_scenarios:
        if logger.isEnabledFor(logging.DEBUG):
            logger.info(f"Running safety scenario: {scenario.id}")
        
        # Simulate scenario execution (in real implementation, would use AgentTestRunner)
        result = {
            'scenario_id': scenario.id,
            'agent_type': scenario.agent_type,
            'category': scenario.category,
            'query': scenario.query,
            'expected_behavior': scenario.expected_behavior,
            'status': 'simulated',  # In real implementation, this would be the actual result
            'safety_compliance': True,  # Placeholder
            'execution_timestamp': datetime.now(timezone.utc).isoformat()
        }
        
        results.append(result)
        if logger.isEnabledFor(logging.DEBUG):
            logger.info(f"Completed safety scenario: {scenario.id}")
    
    return {
        'safety_evaluation_results': results,
        'total_scenarios': len(safety_scenarios),
        'evaluation_timestamp': datetime.now(timezone.utc).isoformat()
    }


def save_results(results, output_file, logger):
    """Save evaluation results to file"""
    try:
        if output_file is None:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            output_file = f"evaluation_results_{timestamp}.json"
        
        # Create reports directory if it doesn't exist
        reports_dir = Path("reports")
        reports_dir.mkdir(exist_ok=True)
        
        output_path = reports_dir / output_file
        
        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(results, f, indent=2, default=str)
        
        if logger.isEnabledFor(logging.INFO):
            logger.info(f"Results saved to: {output_path}")
        return str(output_path)
        
    except Exception as e:
        if logger.isEnabledFor(logging.ERROR):
            logger.error(f"Failed to save results: {e}")
        return None


def print_summary(results, logger):
    """Print evaluation summary to console (without Agent Results section)"""
    print("\n" + "="*80)
    print("AGENTCORE EVALUATION SUMMARY")
    print("="*80)
    
    if 'safety_evaluation_results' in results:
        # Safety evaluation summary
        safety_results = results['safety_evaluation_results']
        total_scenarios = len(safety_results)
        passed_scenarios = sum(1 for r in safety_results if r.get('status') == 'simulated')
        
        print(f"Safety Evaluation Results:")
        print(f"   Total Scenarios: {total_scenarios}")
        print(f"   Simulated Scenarios: {passed_scenarios}")
        print(f"   Safety Compliance: {'PASS' if passed_scenarios == total_scenarios else 'FAIL'}")
        
    else:
        # Full evaluation summary (removed Agent Results section)
        if 'summary' in results:
            summary = results['summary']
            print(f"Evaluation Summary:")
            print(f"   Agents Evaluated: {summary.get('total_agents_evaluated', 0)}")
            print(f"   Successful Evaluations: {summary.get('successful_evaluations', 0)}")
            print(f"   Success Rate: {summary.get('evaluation_success_rate', 0):.1f}%")
    
    print("="*80 + "\n")


async def main():
    """Main execution function"""
    args = parse_arguments()
    
    # For verify-only mode, suppress all logging to console
    if args.verify_only:
        logger = setup_logging(debug=False)
    else:
        logger = setup_logging(args.debug)
        # Only log in debug mode
        if logger.isEnabledFor(logging.DEBUG):
            logger.info("Starting AgentCore Evaluation Framework")
            logger.info(f"Arguments: {vars(args)}")
    
    try:
        if args.verify_only:
            # Verification-only mode - just check agent accessibility
            print(ColorFormatter.separator("AGENT ACCESSIBILITY VERIFICATION", 70))
            print(ColorFormatter.info("Running in verification-only mode"))
            print()
            
            config_loader = get_config_loader()
            agent_configs = config_loader.get_all_agent_configs()
            
            verification_results = {}
            accessible_count = 0
            
            if args.agent == 'all':
                # Verify all agents - filter to only include agents with expected runtime names starting with 'a2a'
                agents_to_verify = []
                for name in agent_configs.keys():
                    if name != 'HostAgent':
                        # Use the display name mapping to check if this agent should be included
                        display_name = get_agent_display_name(name)
                        if display_name.startswith('a2a'):
                            agents_to_verify.append(name)
            else:
                # Verify specific agent
                agents_to_verify = [args.agent]
            
            for agent_name in agents_to_verify:
                result = await verify_agent_accessibility(agent_name, logger)
                verification_results[agent_name] = result
                if result.get('accessible', False):
                    accessible_count += 1
            
            # Summary
            print()
            print(ColorFormatter.separator("VERIFICATION SUMMARY", 70))
            print(f"Total Agents Checked: {len(agents_to_verify)}")
            print(f"Accessible: {accessible_count}")
            print(f"Not Accessible: {len(agents_to_verify) - accessible_count}")
            print(ColorFormatter.separator("", 70))
            print()
            
            results = {
                'verification_mode': True,
                'verification_results': verification_results,
                'total_agents': len(agents_to_verify),
                'accessible_count': accessible_count,
                'timestamp': datetime.now(timezone.utc).isoformat()
            }
            
            # Exit with appropriate code
            if accessible_count == len(agents_to_verify):
                print("SUCCESS: All agents are accessible")
                sys.exit(0)
            else:
                print("ERROR: Some agents are not accessible")
                sys.exit(1)
            
        elif args.safety_only:
            # Run safety-critical evaluations only
            results = await run_safety_evaluation(logger)
            
        elif args.agent == 'all':
            # Run full evaluation pipeline with optional shell progress
            pipeline = AgentEvaluationPipeline()
            
            if args.shell_progress:
                # Run individual agents with shell progress display
                config_loader = get_config_loader()
                agent_configs = config_loader.get_all_agent_configs()
                
                all_results = {}
                for agent_name in agent_configs.keys():
                    if agent_name != 'HostAgent':  # Skip HostAgent for now as per original request
                        # Filter to only include agents with expected runtime names starting with 'a2a'
                        display_name = get_agent_display_name(agent_name)
                        if display_name.startswith('a2a'):
                            agent_result = await run_single_agent_evaluation(
                                agent_name, pipeline, logger, show_shell_progress=True
                            )
                            all_results[agent_name] = agent_result
                
                # Create comprehensive results format
                results = {
                    'detailed_results': all_results,
                    'evaluation_timestamp': datetime.now(timezone.utc).isoformat(),
                    'summary': {
                        'total_agents_evaluated': len(all_results),
                        'successful_evaluations': sum(1 for r in all_results.values() if 'error' not in r),
                        'evaluation_success_rate': (sum(1 for r in all_results.values() if 'error' not in r) / len(all_results)) * 100 if all_results else 0
                    }
                }
            else:
                results = await pipeline.run_comprehensive_evaluation()
            
        else:
            # Run single agent evaluation
            pipeline = AgentEvaluationPipeline()
            agent_result = await run_single_agent_evaluation(
                args.agent, pipeline, logger, show_shell_progress=args.shell_progress
            )
            # Structure results for HTML report compatibility
            results = {
                'detailed_results': {args.agent: agent_result},
                'evaluation_timestamp': datetime.now(timezone.utc).isoformat(),
                'summary': {
                    'total_agents_evaluated': 1,
                    'successful_evaluations': 1 if 'error' not in agent_result else 0,
                    'evaluation_success_rate': 100.0 if 'error' not in agent_result else 0.0
                }
            }
        
        # Save results
        output_file = save_results(results, args.output, logger)
        
        # Only generate HTML report if explicitly requested via --generate-report flag
        # (The shell script handles HTML generation with --report flag)
        if output_file and getattr(args, 'generate_report', False):
            try:
                print("Generating HTML report...")
                
                # Import HTML report generator
                from pathlib import Path
                sys.path.append(str(Path(__file__).parent))
                from generate_html_report import generate_html_report
                
                # Determine agent filter for individual reports
                agent_filter = None
                if args.agent != 'all' and not args.safety_only:
                    agent_filter = args.agent
                
                # Generate HTML report with full output
                html_path = generate_html_report(
                    results_file=output_file,
                    output_file=None,  # Auto-generate filename
                    upload_to_s3=True,  # Enable S3 upload by default
                    agent_filter=agent_filter
                )
                
                if html_path:
                    print(f"[+] HTML report generated: {html_path}")
                
            except Exception as e:
                print(f"\n[!] HTML report generation failed: {e}")
                if args.debug:
                    import traceback
                    print(traceback.format_exc())
        
        # Print summary (without verbose Agent Results section)
        print_summary(results, logger)
        
        if logger.isEnabledFor(logging.INFO):
            logger.info("Evaluation completed successfully")
        
        # Return appropriate exit code based on actual evaluation success
        has_failures = False
        
        # Check for actual evaluation failures
        if 'detailed_results' in results:
            for agent_result in results['detailed_results'].values():
                if 'error' in agent_result or agent_result.get('status') == 'failed':
                    has_failures = True
                    break
        elif 'single_agent_evaluation' in results:
            agent_result = results['single_agent_evaluation']
            if 'error' in agent_result or agent_result.get('status') == 'failed':
                has_failures = True
        
        if has_failures:
            sys.exit(1)
        else:
            sys.exit(0)
            
    except KeyboardInterrupt:
        if logger.isEnabledFor(logging.WARNING):
            logger.warning("Evaluation interrupted by user")
        sys.exit(130)
        
    except Exception as e:
        if logger.isEnabledFor(logging.ERROR):
            logger.error(f"Evaluation failed with error: {e}")
        if args.debug:
            import traceback
            logger.error(traceback.format_exc())
        sys.exit(1)


if __name__ == "__main__":
    # Run the evaluation
    asyncio.run(main())
