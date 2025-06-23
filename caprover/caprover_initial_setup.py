"""
CapRover Initial Setup Script

This script performs a fresh CapRover installation & configures some bare-bones settings.
It generates a configuration file to use next to deploy the application stack.

Usage:
    python caprover_initial_setup.py <IP_ADDRESS> <DOMAIN> <SSL_EMAIL>

Arguments:
    IP_ADDRESS: The IP address of the server where CapRover is installed
    DOMAIN: The domain (or subdomain) to deploy the stack (e.g., mycommunity.example.com)
    SSL_EMAIL: An email address for SSL certificate registration

The script will:
1. Generate a random password for CapRover
2. Set the root domain for CapRover
3. Enable HTTPS with SSL certificates & force HTTPS on connections to the CapRover dashboard
5. Configure automated disk cleanup
6. Output a <domain>.yaml config file (based on stack.example.yaml) for further use:
   see stack_deploy.py

"""

import json
import logging
import secrets
import string
import sys
import time
from pathlib import Path

from caprover_api import caprover_api
from jinja2 import Template

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


def generate_secure_password(length=20):
    """Generate a secure random password."""
    alphabet = string.ascii_letters + string.digits + "!@#$%^&*"
    return "".join(secrets.choice(alphabet) for _ in range(length))


def create_config_file(domain, password):
    """Create a domain-specific config file based on stack.example.yaml."""
    script_dir = Path(__file__).parent
    example_file = script_dir / "stack.example.yaml"
    output_file = script_dir / f"{domain}.yaml"

    # Read the template file as text
    with open(example_file, "r") as f:
        template_content = f.read()

    # Create Jinja2 template and render with values
    template = Template(template_content)
    rendered_content = template.render(
        caprover_url=f"https://captain.{domain}", caprover_password=password
    )

    # Write the rendered configuration file
    with open(output_file, "w") as f:
        f.write(rendered_content)

    logger.info(f"Configuration file saved to: {output_file}")
    return output_file


def caprover_check_errors(cap, response, wait_seconds=15):
    """Check for errors in CapRover API responses and sleep for a few seconds if needed.

    Parameters
    ----------
    cap : CaproverAPI
    response :
    wait_seconds : int
        CapRover often gives nondeterministic failures if you issue automated requests too quickly.
    """
    cap._check_errors(response.json())
    time.sleep(wait_seconds)


def main(ip_address, domain, ssl_email):
    # Generate a secure password
    password = generate_secure_password()
    logger.info("Generated secure password for CapRover")

    logger.info("At the IP of server, set root domain")
    cap = caprover_api.CaproverAPI(
        dashboard_url=f"http://{ip_address}:3000", password=password
    )
    rsp = cap.session.post(
        cap._build_url("/api/v2/user/system/changerootdomain"),
        headers=cap.headers,
        data=json.dumps({"rootDomain": domain, "force": False}),
    )
    caprover_check_errors(cap, rsp)

    logger.info("After a minute, reload, then Enable HTTPs.")
    cap = caprover_api.CaproverAPI(
        dashboard_url=f"http://captain.{domain}", password=password
    )
    rsp = cap.session.post(
        cap._build_url("/api/v2/user/system/enablessl"),
        headers=cap.headers,
        data=json.dumps({"emailAddress": ssl_email}),
    )
    caprover_check_errors(cap, rsp)

    dashboard_url = f"https://captain.{domain}"

    logger.info("Reload to the https:// site, then Force HTTPs.")
    cap = caprover_api.CaproverAPI(dashboard_url=dashboard_url, password=password)
    rsp = cap.session.post(
        cap._build_url("/api/v2/user/system/forcessl"),
        headers=cap.headers,
        data='{"isEnabled":true}',
    )
    caprover_check_errors(cap, rsp)

    logger.info("-> Schedule Disk Cleanup")
    rsp = cap.session.post(
        cap._build_url("/api/v2/user/system/diskcleanup"),
        headers=cap.headers,
        # Keep 2 recent to enable rollback of recent deployments.
        data='{"mostRecentLimit":2,"cronSchedule":"0 21 * * *","timezone":"UTC"}',
    )
    caprover_check_errors(cap, rsp, 0)

    # Create the configuration file
    config_file = create_config_file(domain, password)
    logger.info("CapRover setup completed successfully!")
    logger.info(f"CapRover URL: {dashboard_url}")


if __name__ == "__main__":
    # Check that the correct number of arguments are provided
    if len(sys.argv) != 4:
        print(__doc__)
        print("\nError: Incorrect number of arguments provided.")
        print("Usage: python {} <IP_ADDRESS> <DOMAIN> <SSL_EMAIL>".format(sys.argv[0]))
        print("\nExample:")
        print(
            "  python {} 192.168.1.100 mycommunity.example.com me@example.com".format(
                sys.argv[0]
            )
        )
        sys.exit(1)

    # Assign command-line arguments to variables
    ip_address = sys.argv[1]
    domain = sys.argv[2]
    ssl_email = sys.argv[3]

    main(ip_address, domain, ssl_email)
