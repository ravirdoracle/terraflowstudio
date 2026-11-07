# OCI Database Resources (DB Home, CDB, PDB)

OCI Database resources use the oracle/oci Terraform provider and sit on top of an AWS VM Cluster.
They are generated as three separate modules per database: _dbhome, _cdb, _pdb.

## DB Home (OCI)
Creates an Oracle Database Home on the VM Cluster.

Required:
- vm_cluster_ocid: wired from module.<vmcluster_ref>.ocid (the AWS VM cluster OCID output)

Module outputs: db_home_id

Naming: module prefix + _dbhome, e.g. oci_database_dbhome, oci_db_prod_dbhome

## CDB (Container Database)
Creates the Oracle Container Database inside the DB Home.

Required:
- db_home_id: wired from module.<dbhome>.db_home_id
- admin_password: sensitive, set via TF_VAR_<module_name>_admin_password environment variable

Optional fields:
- db_name: database name, maximum 8 alphanumeric characters, must start with a letter. Default "MYDB"
- db_unique_name: globally unique name, often db_name + suffix e.g. "MYDB_phx1cs"
- character_set: database character set. Default AL32UTF8 (recommended for Unicode)
- ncharacter_set: national character set. Default AL16UTF16
- sid_prefix: SID prefix for the database instances
- auto_backup_enabled: bool, enable automatic backups
- auto_backup_window: backup window e.g. "SLOT_TWO" (02:00-04:00 UTC), "SLOT_EIGHT" (08:00-10:00)
- recovery_window_in_days: backup retention days, default 7

Module outputs: cdb_id

## PDB (Pluggable Database)
Creates a Pluggable Database inside the CDB. Optional — set create_pdb: true to enable.

Required:
- container_database_id: wired from module.<cdb>.cdb_id
- pdb_admin_password: same sensitive var as admin_password

Fields:
- pdb_name: name for the pluggable database, e.g. "MYPDB", "APP_PDB", "HR_PDB"

Module outputs: pdb_id

## OCI Provider authentication
The oracle/oci provider requires:
- oci_tenancy_ocid, oci_user_ocid, oci_fingerprint (for APIKey auth)
- oci_private_key_path: path to ~/.oci/oci_api_key.pem
- oci_region: OCI region e.g. us-ashburn-1, us-phoenix-1
- oci_auth_method: APIKey (default) or InstancePrincipal

Set sensitive values via TF_VAR_ environment variables, never hardcode in files.

## vmcluster_ref
Set vmcluster_ref to the module_name of the AWS VM Cluster that hosts this database.
The DB Home, CDB, and PDB all chain together: dbhome depends on vmcluster, cdb depends on dbhome, pdb depends on cdb.
