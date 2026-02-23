#!/usr/bin/env node
import 'source-map-support/register';
import * as cdk from 'aws-cdk-lib';
import { RootStack } from '../lib/stacks/root-stack';
import { CONFIG } from '../lib/config';

const app = new cdk.App();

new RootStack(app, 'NetAIOpsInfraStack', {
  env: {
    account: CONFIG.account,
    region: CONFIG.primaryRegion,
  },
  description: 'NetAIOps Infrastructure - Modules 5 (K8s Diagnostics) & 6 (Incident Analysis)',
});
