import time
from datetime import datetime, timedelta, timezone
import json
import importlib
import sys, os

import hashlib
from typing import Any

sys.path.append(os.path.abspath("../helperFiles"))
from sqlConnector import MySQLConnection 

try:
    import mysql.connector
except ImportError:
    print("\033[91mmysql.connector is not installed. Run 'pip install mysql-connector-python' \033[0m")

class InnerLayer():
    def __init__(self) -> None:
        self.database = MySQLConnection()
        self.database.setVerbose(False)
        self.database.hazmat_wipe_Table('innerLayer')
        self.database.hazmat_wipe_Table('innerLayerThreats')
        self.devices = {
            "insiderThreat": {'threatLevel': 0, 'logs': {}},
        }
        # self.threat_counts = {} #This may needs to be removed, work in progress
        self.threatTable = {
            "spamCredentials":     0.1,
            "massReporting":       0.2,
            "massAccountCreation": 1,
            "payloadAttack": 1,
            "sqlInjection": 0.4,
            "massCorrelation": 1,
            "jsonCompromised": 0.5,
            "likesInJsonCompromised" : 0.5,
            "locationChange":  0.4,
            "botActivity": 0.4
        }

        #is this in the correct spot?
        self.current_json_hash = self.update_json_hash()

        self.central_analyzer()

    def central_analyzer(self):
        interval = 1
        start_time = time.time()

        while True:
            if time.time() - start_time >= interval:
                self.database.connect()
                self.add_devices()
                ###### Analyzer Functions ######
                
                self.analyze_spam_credentials()

                self.analyze_mass_reporting()

                self.analyze_mass_account_creation_ip()

                self.analyze_mass_correlation()
                
                self.check_payload_increment()
              
                self.analyze_sql_inject()

                self.check_hash_changes()

                self.check_for_new_login()

                self.mass_bot_detection()
  
                ###### Analyzer Functions ######
                

                self.display_Events_and_calc_threat_level()
                start_time = time.time()
                self.database.disconnect()


    def analyze_spam_credentials(self):
        event_type = 'invalidCredentials'
        threatName = "spamCredentials"
        threshold = 20
        time_frame = 1 #Minutes
        current_time = datetime.now(timezone.utc)
        time_limit = current_time - timedelta(minutes=time_frame)

        threat_level = self.threatTable[threatName]
        results = self.database.execute_query(f"SELECT * FROM hybrid_idps.innerLayer WHERE event_type = '{event_type}' AND timestamp >= '{time_limit.strftime('%Y-%m-%d %H:%M:%S')}' ORDER BY timestamp DESC")
        results = self.extract_user(results)

        for user, all_events in results.items():
            count = 0
            for event in all_events:
                count += 1
                if count > threshold:
                    logName = f"{threatName}-{event['timestamp']}"
                    self.add_threat(logName, threatName,  event['username'], event['target_username'], event['ip_address'], event['geolocation'], event['timestamp'],
                                    threatName, threat_level, event['payload'])
                    count = 0

    def analyze_mass_reporting(self):
        event_type = 'reportUserByUsername'
        threatName = "massReporting"
        threshold = 2
        time_frame = 2 #Minutes
        current_time = datetime.now(timezone.utc)
        time_limit = current_time - timedelta(minutes=time_frame)

        threat_level = self.threatTable[threatName]
        results = self.database.execute_query(f"SELECT * FROM hybrid_idps.innerLayer WHERE event_type = '{event_type}' AND timestamp >= '{time_limit.strftime('%Y-%m-%d %H:%M:%S')}' ORDER BY timestamp DESC")
        results = self.extract_user(results)

        for user, user_events in results.items():
            count = 0
            for event in user_events:
                    count += 1
                    if count > threshold:
                        logName = f"{threatName}-{event['timestamp']}"
                        self.add_threat(logName, threatName,  event['username'], event['target_username'], event['ip_address'], event['geolocation'], event['timestamp'],
                                        threatName, threat_level, event['payload'])
                        count = 0

    def analyze_mass_account_creation_ip(self):   
        event_type = 'registrationSuccess'
        threatName = "massAccountCreation"
        threshold = 30
        time_frame = 2 #Minutes
        current_time = datetime.now(timezone.utc)
        time_limit = current_time - timedelta(minutes=time_frame)
        

        threat_level = self.threatTable[threatName]
        results = self.database.execute_query(f"""SELECT ip_address, COUNT(username) AS registration_count
                                                FROM hybrid_idps.innerLayer 
                                                WHERE event_type = '{event_type}' 
                                                AND timestamp >= '{time_limit.strftime('%Y-%m-%d %H:%M:%S')}'
                                                GROUP BY ip_address
                                                HAVING COUNT(username) >= {threshold}""")
        results = self.extract_ips(results)

        for ip, all_event in results.items():
            if all_event[0]['registration_count'] > 1:
                usernames_result = self.database.execute_query(f""" SELECT ip_address, timestamp, username
                                                                    FROM hybrid_idps.innerLayer
                                                                    WHERE ip_address = '{ip}'
                                                                    AND event_type = '{event_type}'
                                                                    AND timestamp >= '{time_limit.strftime('%Y-%m-%d %H:%M:%S')}'""")

                for x in usernames_result:
                    x = list(x.values())
                    ip, timestamp, username = x[0], x[1], x[2]
                    logName = f"{threatName}-{timestamp}"
                    print(f"The ip Address is {ip}")
                    self.add_threat(logName, threatName, username, None, ip, None, timestamp,
                                    threatName, threat_level, None)

    def check_payload_increment(self):
        event_type = 'likePost'
        threatName = "payloadAttack"

        threat_level = self.threatTable[threatName]
        results = self.database.execute_query(f"SELECT * FROM hybrid_idps.innerLayer WHERE event_type = '{event_type}'")
        results = self.extract_payload(results)

        for payload, all_events in results.items():
            for event in all_events:
                payload_dict = json.loads(payload)
                like_increment = payload_dict.get('likeIncrement')
                if like_increment > 1:
                    logName = f"{threatName}-{event['timestamp']}"
                    self.add_threat(logName, threatName,  event['username'], event['target_username'], event['ip_address'], event['geolocation'], event['timestamp'],
                                    threatName, threat_level, event['payload'])
                elif like_increment < -1:
                    logName = f"{threatName}-{event['timestamp']}"
                    self.add_threat(logName, threatName,  event['username'], event['target_username'], event['ip_address'], event['geolocation'], event['timestamp'],
                                    threatName, threat_level, event['payload'])
    
    def analyze_mass_correlation(self):   
            threatName = "massCorrelation"
            user_threshold = 10
            activity_threshold = 10
            time_frame = 2 #Minutes
            current_time = datetime.now(timezone.utc)
            time_limit = current_time - timedelta(minutes=time_frame)

            threat_level = self.threatTable[threatName]

            for event_type in ['reportUserByUsername','friendUserByUsername', 'likePost', 'messageUserByUsername']:

                results = self.database.execute_query(f"""SELECT t.username, t.target_username, t.ip_address, t.timestamp, aggregated_data.user_count
                                                            FROM (
                                                                SELECT target_username, COUNT(DISTINCT username) AS user_count
                                                                FROM hybrid_idps.innerLayer 
                                                                WHERE event_type = '{event_type}' 
                                                                AND timestamp >= '{time_limit.strftime('%Y-%m-%d %H:%M:%S')}'
                                                                GROUP BY target_username
                                                                HAVING COUNT(DISTINCT username) >= {user_threshold}
                                                            ) AS aggregated_data
                                                            JOIN hybrid_idps.innerLayer AS t 
                                                                ON aggregated_data.target_username = t.target_username""")
                results = self.extract_user(results)
    
                for username, rows in results.items():
                        for row in rows:
                            x = list(row.values())
                            username, target_username, ip, timestamp, user_count = x[0], x[1], x[2], x[3], x[4]

                            if user_count > activity_threshold:
                                logName = f"{threatName}-{timestamp}"
                                self.add_threat(logName, threatName, username, target_username, ip, None, timestamp,
                                                event_type, threat_level, None)

    def analyze_sql_inject(self):
        threatName = "sqlInjection"
        threshold = 3
        threat_level = self.threatTable[threatName]
        sqlKeywordCountPayload = 0
        sqlKeywordCountUsername = 0

        sqlKeywords = ["SELECT", "INSERT", "UPDATE", "DELETE", "FROM", "WHERE", "DROP", "TRUNCATE",
                        "UNION", "JOIN", "OR", "AND", "EXEC", "ALTER", "CREATE", "RENAME", "HAVING",
                        "DECLARE", "FETCH", "OPEN", "CLOSE", "CAST", "CONVERT", "EXECUTE", "GRANT", 
                        "REVOKE", "TRIGGER", "MERGE", "WHILE", "BREAK", "COMMIT", "ROLLBACK", "SAVEPOINT",
                        "BEGIN", "END", "'", "\""]
        
        sqlKeywordsLower = [keyword.lower() for keyword in sqlKeywords]
        
        results = self.database.execute_query(f"""SELECT username, payload, ip_address, timestamp
                                                FROM hybrid_idps.innerLayer""")   

        for result in results:
            result = list(result.values())
            username, payload, ip, timestamp = result[0], result[1], result[2], result[3]
            
            sqlPayloadLower = payload.lower() if payload else None
            sqlUsernameLower = username.lower() if username else None

            if sqlPayloadLower:
                sqlKeywordCountPayload = sum(1 for keyword in sqlKeywordsLower if keyword in sqlPayloadLower)
            if sqlUsernameLower:
                sqlKeywordCountUsername = sum(1 for keyword in sqlKeywordsLower if keyword in sqlUsernameLower)
            
            if sqlKeywordCountPayload > threshold or sqlKeywordCountUsername > threshold:
                logName = f"{threatName}-{timestamp}"
                self.add_threat(logName, threatName, username, None, ip, None, timestamp, None, threat_level, None)
    
    def check_hash_changes(self):

        current_time = datetime.now()
        formatted_time = current_time.strftime('%Y-%m-%d %H:%M:%S') 
        threatName = "jsonCompromised"
        threat_level = self.threatTable[threatName]
  
        if self.current_json_hash != self.update_json_hash():
            seconds_window = datetime.now() - timedelta(seconds=6)

            if not self.database.execute_query(f"SELECT * FROM hybrid_idps.innerLayer WHERE SECOND(timestamp) >= {seconds_window.second}"):
                print("tampered")
                logName = f"{threatName}-{current_time}"
                self.add_threat(logName, threatName, None, None, None, None, formatted_time,
                                     threatName, threat_level, None, True)

            self.current_json_hash = self.update_json_hash()
        
    def update_json_hash(self):
        
        try:
            with open('registeredUsers.json', 'rb') as file:
                current_hash = hashlib.sha256(file.read()).hexdigest()
        except FileNotFoundError:
            print(f"File not found: {'registeredUsers.json'}")
        
        return current_hash

    def parse_and_sum_payload(self, results):
        data =  [list(json.loads(result['payload']).values())[1:] for result in results]
        result_dict = {}
        for entry in data:
            id, value = entry  
            if id in result_dict:
                result_dict[id] += value
            else:
                result_dict[id] = value

        return result_dict
   
    def check_for_new_login(self):
        
        seconds_window = datetime.now() - timedelta(seconds=10)
        newLogins = self.database.execute_query(f"SELECT * FROM hybrid_idps.innerLayer WHERE event_type = 'successfulLogin' AND SECOND(timestamp) >= {seconds_window.second}")

        for user in newLogins:
            self.check_geo_changes(user)

    def check_geo_changes(self, results):
        
        threatName = "locationChange"
        threat_level = self.threatTable[threatName]
        logName = f"{threatName}-{results['timestamp']}"

        geolocation = results['geolocation']
        currentUser = results['username']

        pastLogin = self.database.execute_query(f"""SELECT * FROM hybrid_idps.innerLayer 
                                                WHERE event_type = 'successfulLogin' 
                                                AND timestamp < ( SELECT MAX(timestamp) 
                                                FROM hybrid_idps.innerLayer 
                                                WHERE event_type = 'successfulLogin') 
                                                ORDER BY timestamp DESC LIMIT 1""")
        
        if pastLogin:
            pastLoginLocation = pastLogin[0]['geolocation']
        
            if geolocation != pastLoginLocation:

                self.add_threat(logName, threatName, results['username'], None, results['ip_address'], geolocation,
                            results['timestamp'], threatName, threat_level, None)
            
    def mass_bot_detection(self):
        threatName = "botActivity"
        threshold = 2
        time_frame = 2 #Minutes
        current_time = datetime.now(timezone.utc)
        time_limit = current_time - timedelta(minutes=time_frame)

        threat_level = self.threatTable[threatName]
        results = self.database.execute_query(f"SELECT * FROM hybrid_idps.innerLayer WHERE event_type IN ('reportUserByUsername','likePost', 'addComment') AND timestamp >= '{time_limit.strftime('%Y-%m-%d %H:%M:%S')}' ORDER BY timestamp DESC")
        results = self.extract_user(results)

        for user, user_events in results.items():
            count = 0
            for event in user_events:
                    count += 1
                    if count > threshold:
                        logName = f"{threatName}-{event['timestamp']}"
                        self.add_threat(logName, threatName,  event['username'], event['target_username'], event['ip_address'], event['geolocation'], event['timestamp'],
                                        threatName, threat_level, event['payload'])
                        count = 0

        
        
    def display_Events_and_calc_threat_level(self):
        for username, deviceData in self.devices.items():
            print("\n")
            print(f"username: {username}")
            logs = deviceData["logs"]
            threatLevel = 0
            for threatName, threadType in logs.items():
                print(f"        {threatName}")
                threatLevel += self.threatTable[threadType]
                
            if threatLevel > 1: threatLevel = 1
            self.set_threat_level(username, threatLevel)
            color_code = "\033[92m"  # Green
            if threatLevel > 0.5:
                color_code = "\033[91m"  # Red
            elif 0 < threatLevel < 0.5:
                color_code = "\033[93m"  # Yellow
            reset_color = "\033[0m"
            print(f"{color_code}[Threat Level]:   {threatLevel} {reset_color}")
            
    def extract_ips(self, results):
        ip_dict = {}
        for entry in results:
            ip = entry['ip_address']
            if ip not in ip_dict:
                ip_dict[ip] = []
            ip_dict[ip].append(entry)
        return ip_dict
    
    def extract_geo(self, results):
        geo_dict = {}
        for entry in results:
            geo = entry['geolocation']
            if geo not in geo_dict:
                geo_dict[geo] = []
            geo_dict[geo].append(entry)
        return geo_dict
    
    def extract_user(self, results):
        user_dict = {}
        for entry in results:
            user = entry['username']
            if user not in user_dict:
                user_dict[user] = []
            user_dict[user].append(entry)
        return user_dict

    def extract_payload(self, results):
        payload_dict = {}
        for entry in results:
            payload = entry['payload']
            if payload not in payload_dict:
                payload_dict[payload] = []
            payload_dict[payload].append(entry)
        return payload_dict
    
    def parse_payload(self, results):
        return [list(json.loads(result['payload']).values()) for result in results]
 
    def otherstuff(data):
        result_dict = {}
        for entry in data:
            id, value = entry  
            if id in result_dict:
                result_dict[id] += value
            else:
                result_dict[id] = value

        return result_dict

    def add_devices(self):
        results = self.database.execute_query(f"SELECT DISTINCT username from hybrid_idps.innerLayer")
        usernameList = [result['username'] for result in results] #Possibly IPV6
        
        for username in usernameList:
            # if ip.startswith("::ffff:"):     # ip_address ::ffff:192.168.1.99
            #     ip = ip.split(":")[-1]       # ip_address 192.168.1.99
            if username not in self.devices:
                self.devices[username] = {'threatLevel': 0, 'logs': {}}   
        
    def add_threat(self, logName, threatName, username, target_username, ip_address, geolocation, timestamp, event_type, threat_level, payload, hazmat_add_directly_to_database = False):
        
        if hazmat_add_directly_to_database:
            device = self.devices["insiderThreat"]
            if logName not in device['logs']:
                device['logs'][logName] = threatName
                self.database.add_threat_to_inner_Layer_Threats_DB(username, target_username, ip_address, geolocation, timestamp, event_type, threat_level, payload)
            return
        
        if ip_address and ip_address.startswith("::ffff:"):     # ip_address ::ffff:192.168.1.99
            ip_address = ip_address.split(":")[-1] # ip_address 192.168.1.99
        
        
        if username in self.devices:
            device = self.devices[username]
            threatLevel = self.threatTable[threatName]

            if logName not in device['logs']:
                device = self.devices[username]
                device['logs'][logName] = threatName
                self.database.add_threat_to_inner_Layer_Threats_DB(username, target_username, ip_address, geolocation, timestamp, event_type, threat_level, payload)
                
        else:
            print(f"Failed to add_threat. Device with IP address {ip_address} does not exist.")


            
    def set_threat_level(self, username, newThreatLevel):
        if username in self.devices:
            device = self.devices[username]['threatLevel'] = newThreatLevel
        else:
            print(f"Failed to set_threat_level. Device with username {username} does not exist.")

if __name__ == "__main__":
    x = InnerLayer()
