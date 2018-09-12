#
# This file made available under CC0 1.0 Universal (https://creativecommons.org/publicdomain/zero/1.0/legalcode)
#
# Created with the Rule Development Kit: https://github.com/awslabs/aws-config-rdk
# Can be used stand-alone or with the Rule Compliance Engine: https://github.com/awslabs/aws-config-engine-for-compliance-as-code
#
"""
#####################################
##           Gherkin               ##
#####################################

Rule Name:
	emr_kerberos_enabled

Description:
	Checks that EMR clusters have Kerberos Enabled

Trigger:
  Periodic

Resource Type to report on:
	AWS::EMR::Cluster

Rule Parameters:
        | ---------------------| --------- | --------------------------------------------- | ------------------------------ |
        | Parameter Name       | Type      | Description                                   | Notes                          |
        | ---------------------| --------- | --------------------------------------------- | ------------------------------ |
        | TicketLifetimeInHours| Optional  | Period for which Kerberos ticket issued by    | must be equal to or less than  |
        |                      |           | cluster's KDC is valid                        | parameter                      |
        | ---------------------| --------- | --------------------------------------------- | ------------------------------ |
        | Realm                | Optional  | Kereberos Realm name of the other realm in    | must be equal to parameter     |
        |                      |           | the trust relationship                        |                                |
        | ---------------------| --------- | --------------------------------------------- | ------------------------------ |
        | Domain               | Optional  | Domain name of the other realm in the trust   | must be equal to parameter     |
        |                      |           | relationship                                  |                                |
        | ---------------------| --------- | --------------------------------------------- | ------------------------------ |
        | AdminServer          | Optional  | Fully qualified domain of the admin server in | must be equal to parameter     |
        |                      |           | the other realm of the trust relationship     |                                |
        | ---------------------| --------- | --------------------------------------------- | ------------------------------ |
        | KdcServer            | Optional  | Fully qualified domain of the KDC server in   | must be equal to parameter     |
        |                      |           | the other realm of the trust relationship     |                                |
        | ---------------------| --------- | --------------------------------------------- | ------------------------------ |

Feature:
	In order to: enforce our Security Policies
	         As: a Security Officer
	     I want: to ensure that EMR Clusters have Kerberos authentication enabled

Scenarios:
  Scenario 1:
  Given: The parameter TicketLifetimeInHours is configured
    And: the parameter is not a numeric value
   Then: Return an error

  Scenario 2:
  Given: The parameter Realm is configured
    And: the parameter is not in capital letters
   Then: Return an error

  Scenario 3:
  Given: The parameter Domain is configured
    And: the parameter is not valid
   Then: Return an error

  Scenario 4:
  Given: The parameter AdminServer is configured
    And: the parameter is not an alphanumeric value
   Then: Return an error

  Scenario 5:
  Given: The parameter KdcServer is configured
    And: the parameter is not an alphanumeric value
   Then: Return an error

  Scenario 6:
	Given: An EMR cluster is terminating, terminated or terminated with errors
	 Then: Do not evaluate

  Scenario 7:
	Given: No EMR cluster is running
	 Then: Return Compliant

  Scenario 8:
	Given: An EMR cluster is running
    And: No security configuration is attached to the cluster
   Then: Return Non_Compliant

  Scenario 9:
  Given: An EMR cluster is running
    And: Security configuration is attached to the cluster
    And: The Parameter TicketLifetimeInHours or Realm or Domain or AdminServer or KdcServer is configured and not valid
   Then: Return Non_Compliant

  Scenario 10:
  Given: An EMR cluster is running
    And: Security configuration is attached to the cluster
    And: The Parameter TicketLifetimeInHours or Realm or Domain or AdminServer or KdcServer is configured and valid
   Then: Return Compliant
"""
import json
import datetime
import re
import boto3
import botocore

##############
# Parameters #
##############

# Define the default resource to report to Config Rules
DEFAULT_RESOURCE_TYPE = 'AWS::EMR::Cluster'

# Set to True to get the lambda to assume the Role attached on the Config Service (useful for cross-account).
ASSUME_ROLE_MODE = False

#############
# Main Code #
#############

def evaluate_compliance(event, configuration_item, rule_parameters):
    """Form the evaluation(s) to be return to Config Rules

    Return either:
    None -- when no result needs to be displayed
    a string -- either COMPLIANT, NON_COMPLIANT or NOT_APPLICABLE
    a dictionary -- the evaluation dictionary, usually built by build_evaluation_from_config_item()
    a list of dictionary -- a list of evaluation dictionary , usually built by build_evaluation()

    Keyword arguments:
    event -- the event variable given in the lambda handler
    configuration_item -- the configurationItem dictionary in the invokingEvent
    valid_rule_parameters -- the output of the evaluate_parameters() representing validated parameters of the Config Rule

    Advanced Notes:
    1 -- if a resource is deleted and generate a configuration change with ResourceDeleted status, the Boilerplate code will put a NOT_APPLICABLE on this resource automatically.
    2 -- if a None or a list of dictionary is returned, the old evaluation(s) which are not returned in the new evaluation list are returned as NOT_APPLICABLE by the Boilerplate code
    3 -- if None or an empty string, list or dict is returned, the Boilerplate code will put a "shadow" evaluation to feedback that the evaluation took place properly
    """
    evaluations = []

    emr_client = get_client('emr', event)
    
    cluster_list = get_all_cluster(emr_client)
    
    if not cluster_list:
        return None
    
    for cluster in cluster_list:

        cluster_id = cluster["Id"]
        described_cluster = emr_client.describe_cluster(ClusterId=cluster_id)["Cluster"]

        if described_cluster["Status"]["State"] in ["TERMINATING", "TERMINATED", "TERMINATED_WITH_ERRORS"]:
            evaluations.append(build_evaluation(cluster_id, 'NOT_APPLICABLE', event))
            continue
            
        if "SecurityConfiguration" not in described_cluster:
            evaluations.append(build_evaluation(cluster_id, 'NON_COMPLIANT', event, annotation='No Security Configuration is attached.'))
            continue
   
        cluster_sc_details = json.loads(emr_client.describe_security_configuration(
            Name=described_cluster["SecurityConfiguration"]
                )["SecurityConfiguration"])

        if "AuthenticationConfiguration" not in cluster_sc_details or \
            "KerberosConfiguration" not in cluster_sc_details["AuthenticationConfiguration"] or \
            "ClusterDedicatedKdcConfiguration" not in cluster_sc_details["AuthenticationConfiguration"]["KerberosConfiguration"]:
            evaluations.append(build_evaluation(cluster_id, 'NON_COMPLIANT', event, annotation='Kerberos Authentication is not enabled in the Security Configuration.'))
            continue

        sc_kerberos_details = cluster_sc_details["AuthenticationConfiguration"]["KerberosConfiguration"]["ClusterDedicatedKdcConfiguration"]
        if "TicketLifetimeInHours" in rule_parameters:
            if sc_kerberos_details["TicketLifetimeInHours"] < rule_parameters["TicketLifetimeInHours"]:
                evaluations.append(build_evaluation(cluster_id, 'NON_COMPLIANT', event, annotation='TicketLifetimeInHours is smaller than the specified Rule parameter TicketLifetimeInHours.'))
                continue

        if "CrossRealmTrustConfiguration" not in sc_kerberos_details:
            evaluations.append(build_evaluation(cluster_id, 'NON_COMPLIANT', event, annotation='CrossRealmTrustConfiguration is not configured in security configuration.'))
            continue

        sc_kerberos_details = sc_kerberos_details["CrossRealmTrustConfiguration"]

        if "Realm" in rule_parameters:
            if not str(sc_kerberos_details["Realm"]).__eq__(rule_parameters["Realm"]):
                evaluations.append(build_evaluation(cluster_id, 'NON_COMPLIANT', event, annotation='Realm is not equal to the specified Rule parameter Realm.'))
                continue

        if "Domain" in rule_parameters:
            if not str(sc_kerberos_details["Domain"]).__eq__(rule_parameters["Domain"]):
                evaluations.append(build_evaluation(cluster_id, 'NON_COMPLIANT', event, annotation='Domain is not equal to the specified Rule parameter Domain.'))
                continue

        if "AdminServer" in rule_parameters:
            if not str(sc_kerberos_details["AdminServer"]).__eq__(rule_parameters["AdminServer"]):
                evaluations.append(build_evaluation(cluster_id, 'NON_COMPLIANT', event, annotation='AdminServer is not equal to the specified Rule parameter AdminServer.'))
                continue

        if "KdcServer" in rule_parameters:
            if not str(sc_kerberos_details["KdcServer"]).__eq__(rule_parameters["KdcServer"]):
                evaluations.append(build_evaluation(cluster_id, 'NON_COMPLIANT', event, annotation='KdcServer is not equal to the specified Rule parameter KdcServer.'))
                continue

        evaluations.append(build_evaluation(cluster_id, 'COMPLIANT', event))
        continue

    return evaluations

def get_all_cluster(client):
    clusters = client.list_clusters()
    all_clusters = []
    while True:
        all_clusters += clusters['Clusters']
        if "Marker" in clusters:
            clusters = client.list_clusters(Marker=clusters["Marker"])
        else:
            break
    return all_clusters

def evaluate_parameters(rule_parameters):
    
    if not rule_parameters:
        return {}
    if "TicketLifetimeInHours" in rule_parameters and not str(rule_parameters["TicketLifetimeInHours"]).isnumeric():
        raise ValueError("TicketLifetimeInHours")
    if "Realm" in rule_parameters and (not str(rule_parameters["Realm"]).isupper() or not is_valid_hostname(
            rule_parameters["Realm"], "DOMAIN")):
        raise ValueError("Realm")
    if "Domain" in rule_parameters and not is_valid_hostname(rule_parameters["Domain"], "DOMAIN"):
        raise ValueError("Domain")
    if "AdminServer" in rule_parameters and not is_valid_hostname(rule_parameters["AdminServer"], "FQDN"):
        raise ValueError("AdminServer")
    if "KdcServer" in rule_parameters and not is_valid_hostname(rule_parameters["KdcServer"], "FQDN"):
        raise ValueError("KdcServer")
    return rule_parameters

def is_valid_hostname(hostname, type):
    if len(hostname) > 255:
        return False
    if hostname[-1] == ".":
        hostname = hostname[:-1]  # strip exactly one dot from the right, if present
    if str(type).__eq__("FQDN"):
        fqdn = hostname.split(":")
        if len(fqdn) > 1 and not str(fqdn[1]).isnumeric():
            return False
        hostname = fqdn[0]
    if len(hostname.split(".")) < 2:
        return False
    allowed = re.compile("(?!-)[A-Z\d-]{1,63}(?<!-)$", re.IGNORECASE)
    return all(allowed.match(x) for x in hostname.split("."))

####################
# Helper Functions #
####################

# Build an error to be displayed in the logs when the parameter is invalid.
def build_parameters_value_error_response(ex):
    """Return an error dictionary when the evaluate_parameters() raises a ValueError.

    Keyword arguments:
    ex -- Exception text
    """
    return  build_error_response(internalErrorMessage="Customer error while parsing input parameters",
                                 internalErrorDetails="Parameter value is invalid",
                                 customerErrorCode="InvalidParameterValueException",
                                 customerErrorMessage=str(ex))

# This gets the client after assuming the Config service role
# either in the same AWS account or cross-account.
def get_client(service, event):
    """Return the service boto client. It should be used instead of directly calling the client.

    Keyword arguments:
    service -- the service name used for calling the boto.client()
    event -- the event variable given in the lambda handler
    """
    if not ASSUME_ROLE_MODE:
        return boto3.client(service)
    credentials = get_assume_role_credentials(event["executionRoleArn"])
    return boto3.client(service, aws_access_key_id=credentials['AccessKeyId'],
                        aws_secret_access_key=credentials['SecretAccessKey'],
                        aws_session_token=credentials['SessionToken']
                       )

# This generate an evaluation for config
def build_evaluation(resource_id, compliance_type, event, resource_type=DEFAULT_RESOURCE_TYPE, annotation=None):
    """Form an evaluation as a dictionary. Usually suited to report on scheduled rules.

    Keyword arguments:
    resource_id -- the unique id of the resource to report
    compliance_type -- either COMPLIANT, NON_COMPLIANT or NOT_APPLICABLE
    event -- the event variable given in the lambda handler
    resource_type -- the CloudFormation resource type (or AWS::::Account) to report on the rule (default DEFAULT_RESOURCE_TYPE)
    annotation -- an annotation to be added to the evaluation (default None)
    """
    eval_cc = {}
    if annotation:
        eval_cc['Annotation'] = annotation
    eval_cc['ComplianceResourceType'] = resource_type
    eval_cc['ComplianceResourceId'] = resource_id
    eval_cc['ComplianceType'] = compliance_type
    eval_cc['OrderingTimestamp'] = str(json.loads(event['invokingEvent'])['notificationCreationTime'])
    return eval_cc

def build_evaluation_from_config_item(configuration_item, compliance_type, annotation=None):
    """Form an evaluation as a dictionary. Usually suited to report on configuration change rules.

    Keyword arguments:
    configuration_item -- the configurationItem dictionary in the invokingEvent
    compliance_type -- either COMPLIANT, NON_COMPLIANT or NOT_APPLICABLE
    annotation -- an annotation to be added to the evaluation (default None)
    """
    eval_ci = {}
    if annotation:
        eval_ci['Annotation'] = annotation
    eval_ci['ComplianceResourceType'] = configuration_item['resourceType']
    eval_ci['ComplianceResourceId'] = configuration_item['resourceId']
    eval_ci['ComplianceType'] = compliance_type
    eval_ci['OrderingTimestamp'] = configuration_item['configurationItemCaptureTime']
    return eval_ci

####################
# Boilerplate Code #
####################

# Helper function used to validate input
def check_defined(reference, reference_name):
    if not reference:
        raise Exception('Error: ', reference_name, 'is not defined')
    return reference

# Check whether the message is OversizedConfigurationItemChangeNotification or not
def is_oversized_changed_notification(message_type):
    check_defined(message_type, 'messageType')
    return message_type == 'OversizedConfigurationItemChangeNotification'

# Check whether the message is a ScheduledNotification or not.
def is_scheduled_notification(message_type):
    check_defined(message_type, 'messageType')
    return message_type == 'ScheduledNotification'

# Get configurationItem using getResourceConfigHistory API
# in case of OversizedConfigurationItemChangeNotification
def get_configuration(resource_type, resource_id, configuration_capture_time):
    result = AWS_CONFIG_CLIENT.get_resource_config_history(
        resourceType=resource_type,
        resourceId=resource_id,
        laterTime=configuration_capture_time,
        limit=1)
    configurationItem = result['configurationItems'][0]
    return convert_api_configuration(configurationItem)

# Convert from the API model to the original invocation model
def convert_api_configuration(configurationItem):
    for k, v in configurationItem.items():
        if isinstance(v, datetime.datetime):
            configurationItem[k] = str(v)
    configurationItem['awsAccountId'] = configurationItem['accountId']
    configurationItem['ARN'] = configurationItem['arn']
    configurationItem['configurationStateMd5Hash'] = configurationItem['configurationItemMD5Hash']
    configurationItem['configurationItemVersion'] = configurationItem['version']
    configurationItem['configuration'] = json.loads(configurationItem['configuration'])
    if 'relationships' in configurationItem:
        for i in range(len(configurationItem['relationships'])):
            configurationItem['relationships'][i]['name'] = configurationItem['relationships'][i]['relationshipName']
    return configurationItem

# Based on the type of message get the configuration item
# either from configurationItem in the invoking event
# or using the getResourceConfigHistiry API in getConfiguration function.
def get_configuration_item(invokingEvent):
    check_defined(invokingEvent, 'invokingEvent')
    if is_oversized_changed_notification(invokingEvent['messageType']):
        configurationItemSummary = check_defined(invokingEvent['configurationItemSummary'], 'configurationItemSummary')
        return get_configuration(configurationItemSummary['resourceType'], configurationItemSummary['resourceId'], configurationItemSummary['configurationItemCaptureTime'])
    elif is_scheduled_notification(invokingEvent['messageType']):
        return None
    return check_defined(invokingEvent['configurationItem'], 'configurationItem')

# Check whether the resource has been deleted. If it has, then the evaluation is unnecessary.
def is_applicable(configurationItem, event):
    try:
        check_defined(configurationItem, 'configurationItem')
        check_defined(event, 'event')
    except:
        return True
    status = configurationItem['configurationItemStatus']
    eventLeftScope = event['eventLeftScope']
    if status == 'ResourceDeleted':
        print("Resource Deleted, setting Compliance Status to NOT_APPLICABLE.")
    return (status == 'OK' or status == 'ResourceDiscovered') and not eventLeftScope

def get_assume_role_credentials(role_arn):
    sts_client = boto3.client('sts')
    try:
        assume_role_response = sts_client.assume_role(RoleArn=role_arn, RoleSessionName="configLambdaExecution")
        return assume_role_response['Credentials']
    except botocore.exceptions.ClientError as ex:
        # Scrub error message for any internal account info leaks
        print(str(ex))
        if 'AccessDenied' in ex.response['Error']['Code']:
            ex.response['Error']['Message'] = "AWS Config does not have permission to assume the IAM role."
        else:
            ex.response['Error']['Message'] = "InternalError"
            ex.response['Error']['Code'] = "InternalError"
        raise ex

# This removes older evaluation (usually useful for periodic rule not reporting on AWS::::Account).
def clean_up_old_evaluations(latest_evaluations, event):

    cleaned_evaluations = []

    old_eval = AWS_CONFIG_CLIENT.get_compliance_details_by_config_rule(
        ConfigRuleName=event['configRuleName'],
        ComplianceTypes=['COMPLIANT', 'NON_COMPLIANT'],
        Limit=100)

    old_eval_list = []

    while True:
        for old_result in old_eval['EvaluationResults']:
            old_eval_list.append(old_result)
        if 'NextToken' in old_eval:
            next_token = old_eval['NextToken']
            old_eval = AWS_CONFIG_CLIENT.get_compliance_details_by_config_rule(
                ConfigRuleName=event['configRuleName'],
                ComplianceTypes=['COMPLIANT', 'NON_COMPLIANT'],
                Limit=100,
                NextToken=next_token)
        else:
            break

    for old_eval in old_eval_list:
        old_resource_id = old_eval['EvaluationResultIdentifier']['EvaluationResultQualifier']['ResourceId']
        newer_founded = False
        for latest_eval in latest_evaluations:
            if old_resource_id == latest_eval['ComplianceResourceId']:
                newer_founded = True
        if not newer_founded:
            cleaned_evaluations.append(build_evaluation(old_resource_id, "NOT_APPLICABLE", event))

    return cleaned_evaluations + latest_evaluations

# This decorates the lambda_handler in rule_code with the actual PutEvaluation call
def lambda_handler(event, context):

    global AWS_CONFIG_CLIENT

    #print(event)
    check_defined(event, 'event')
    invoking_event = json.loads(event['invokingEvent'])
    rule_parameters = {}
    if 'ruleParameters' in event:
        rule_parameters = json.loads(event['ruleParameters'])

    try:
        valid_rule_parameters = evaluate_parameters(rule_parameters)
    except ValueError as ex:
        return build_parameters_value_error_response(ex)

    try:
        AWS_CONFIG_CLIENT = get_client('config', event)
        if invoking_event['messageType'] in ['ConfigurationItemChangeNotification', 'ScheduledNotification', 'OversizedConfigurationItemChangeNotification']:
            configuration_item = get_configuration_item(invoking_event)
            if is_applicable(configuration_item, event):
                compliance_result = evaluate_compliance(event, configuration_item, valid_rule_parameters)
            else:
                compliance_result = "NOT_APPLICABLE"
        else:
            return build_internal_error_response('Unexpected message type', str(invoking_event))
    except botocore.exceptions.ClientError as ex:
        if is_internal_error(ex):
            return build_internal_error_response("Unexpected error while completing API request", str(ex))
        return build_error_response("Customer error while making API request", str(ex), ex.response['Error']['Code'], ex.response['Error']['Message'])
    except ValueError as ex:
        return build_internal_error_response(str(ex), str(ex))

    evaluations = []
    latest_evaluations = []

    if not compliance_result:
        latest_evaluations.append(build_evaluation(event['accountId'], "NOT_APPLICABLE", event, resource_type='AWS::::Account'))
        evaluations = clean_up_old_evaluations(latest_evaluations, event)
    elif isinstance(compliance_result, str):
        evaluations.append(build_evaluation_from_config_item(configuration_item, compliance_result))
    elif isinstance(compliance_result, list):
        for evaluation in compliance_result:
            missing_fields = False
            for field in ('ComplianceResourceType', 'ComplianceResourceId', 'ComplianceType', 'OrderingTimestamp'):
                if field not in evaluation:
                    print("Missing " + field + " from custom evaluation.")
                    missing_fields = True

            if not missing_fields:
                latest_evaluations.append(evaluation)
        evaluations = clean_up_old_evaluations(latest_evaluations, event)
    elif isinstance(compliance_result, dict):
        missing_fields = False
        for field in ('ComplianceResourceType', 'ComplianceResourceId', 'ComplianceType', 'OrderingTimestamp'):
            if field not in compliance_result:
                print("Missing " + field + " from custom evaluation.")
                missing_fields = True
        if not missing_fields:
            evaluations.append(compliance_result)
    else:
        evaluations.append(build_evaluation_from_config_item(configuration_item, 'NOT_APPLICABLE'))

    # Put together the request that reports the evaluation status
    resultToken = event['resultToken']
    testMode = False
    if resultToken == 'TESTMODE':
        # Used solely for RDK test to skip actual put_evaluation API call
        testMode = True
    # Invoke the Config API to report the result of the evaluation
    while(evaluations):
        AWS_CONFIG_CLIENT.put_evaluations(Evaluations=evaluations[:100], ResultToken=resultToken, TestMode=testMode)
        del evaluations[:100]
    # Used solely for RDK test to be able to test Lambda function
    return evaluations

def is_internal_error(exception):
    return ((not isinstance(exception, botocore.exceptions.ClientError)) or exception.response['Error']['Code'].startswith('5')
            or 'InternalError' in exception.response['Error']['Code'] or 'ServiceError' in exception.response['Error']['Code'])

def build_internal_error_response(internalErrorMessage, internalErrorDetails=None):
    return build_error_response(internalErrorMessage, internalErrorDetails, 'InternalError', 'InternalError')

def build_error_response(internalErrorMessage, internalErrorDetails=None, customerErrorCode=None, customerErrorMessage=None):
    error_response = {
        'internalErrorMessage': internalErrorMessage,
        'internalErrorDetails': internalErrorDetails,
        'customerErrorMessage': customerErrorMessage,
        'customerErrorCode': customerErrorCode
    }
    print(error_response)
    return error_response
