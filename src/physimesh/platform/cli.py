"""Trusted operator provisioning; passwords come from runtime environment, never arguments."""
import argparse
import json
import os


def main():
    from physimesh.api.app import create_app
    from physimesh.api.settings import load_settings
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=('provision',))
    parser.add_argument('--email', required=True)
    parser.add_argument('--organization')
    parser.add_argument('--issuer')
    parser.add_argument('--subject')
    args = parser.parse_args()
    app = create_app(load_settings(os.environ))
    if not app.state.settings.hosted_mode:
        raise ValueError('provisioning requires explicit hosted mode')
    try:
        user = app.state.identity.provision(args.email, password=os.environ.get('PHYSIMESH_PROVISION_PASSWORD'),
                                             issuer=args.issuer, subject=args.subject)
        record = {'user_id': user}
        if args.organization:
            record['org_id'] = app.state.identity.organization(user, args.organization)
        print(json.dumps(record))
    finally:
        app.state.metadata.close()


if __name__ == '__main__':
    main()
