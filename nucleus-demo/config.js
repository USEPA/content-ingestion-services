const path = require('path');

module.exports = {
  /**
   * The port to run Nucleus Server on, if the port is in use the server will not start
   */
  port: 3030,

  /**
   * The fully qualified domain + path that Nucleus is being hosted at
   */
  baseURL: 'http://localhost:8888',

  /**
   * The data store to use when persisting plugins and versions.  Current possible values
   * are "sequelize", ensure you also supply valid connection details for your
   * chosen strategy below.
   *
   * PR's welcome to add another data store.
   */
  dbStrategy: 'sequelize',

  /**
   * Sequelize connection information, please note all options are required
   *
   * database: The name of the database to connect to
   * dialect: The type of SQL database this is, check sequelize docs for more info
   * username: Username to use when connecting
   * password; Password to use when connecting
   * host: Hostname of database
   * port: Port to use when connecting
   * storage: Path to sqlite file, only used for sqlite dialect
   */
  sequelize: {
    dialect: 'sqlite',
    storage: path.resolve(__dirname, 'db.sqlite'),
  },

  /**
   * The file store to use when persisting update files and metadata.  Current possible
   * values are "s3" and "local" ensure you also supply valid connection details if
   * required for your chosen strategy below.
   *
   * PR's welcome to add another file store.
   */
  fileStrategy: 'local',

  /**
   * Local file configuration
   *
   * root: Path on disk to the root of the static file store
   * staticUrl: The HTTP url to use to access the static file store remotely
   */
  local: {
    root: path.resolve(__dirname, '.files'),
    staticUrl: 'http://localhost:9999'
  },

  /**
   * There is actually no authentication config for s3, all config must be done through the standard AWS
   * environment variables or through EC2 IAM roles.
   *
   * See http://docs.aws.amazon.com/sdk-for-javascript/v2/developer-guide/setting-credentials-node.html
   *
   * Bucket / Region / CloudFront config goes here though
   */
  s3: {
    // init: {
    //   endpoint: '' // The alternate endpoint to reach the S3 instance at,
    //   s3ForcePathStyle: true // Always use path style URLs
    // }

    bucketName: '', // The name for your S3 Bucket

    cloudfront: { // If you don't have CloudFront set up and just want to use the S3 bucket set this to "null
      distributionId: '', // The CloudFront distribution ID, used for invalidating files
      publicUrl: '', // Fully qualified URL for the root of the CloudFront proxy for the S3 bucket
    }
  },

  /**
   * The authentication strategy to use when logging users in.  Current possible values are "local",
   * "openid" and "github".  Make you also supply the required authentication details
   */
  authStrategy: 'local',

  /**
   * Local authentication details
   *
   * The `adminIdentifiers` array should be a list of usernames
   *
   * DISCLAIMER: This strategy should ONLY be used for local development and NEVER
   * used in production.  Unicorns cry every time this setting is used in production.
   * Don't make the unicorns cry.
   *
   * displayName: The user friendly name of this user
   * username: A unique identifier to use when this user signs in, please note uniqueness is
   *           not enforced
   * password: Well, uhhh, their password
   * photo: A URL for their profile, entirely optional, just makes things look nicer ;)
   */
  localAuth: [{
    displayName: 'Charlie',
    username: 'charlie',
    password: 'charlie',
    photo: 'https://pbs.twimg.com/profile_images/1219364727/charlie-support_400x400.png'
  }],

  /**
   * OpenID authentication details
   *
   * The `adminIdentifiers` array should be a list of email
   * addresses for users to consider admins
   *
   * realm: The domain that the server is hosted on
   * stateless: Stateless mode for openID
   * profile: Whether to fetch profile information, should normally be true
   * providerURL: Your openID provider URL
   * domain: Domain to restrict email addresses to
   */
  openid: {
    realm: 'http://localhost:8888',
    stateless: true,
    profile: true,
    providerURL: 'https://auth.myservice.com/openid/v2/op',
    domain: 'myservice.com'
  },

  /**
   * GitHub authentication details
   *
   * The `adminIdentifiers` array should be a list of GitHub usernames
   * to consider admins
   *
   * clientID: GitHub API client ID
   * clientSecret: GitHub API clientSecret
   * realm: The domain the server is hosted on
   */
  github: {
    clientID: '',
    clientSecret: ''
  },

  /**
   * See the documentation for your authentication strategy for what this array does
   */
  adminIdentifiers: ['admin@yourdomain.com', 'charlie'],

  /**
   * Session options, in development just leave this as default.
   *
   * IN PRODUCTION PLEASE USE REDIS!
   *
   * type: Can be either "redis" or null
   *
   * redis:
   *   host: The host URL for the redis instance
   *   port: The port for the redis instance
   */
  sessionConfig: {
    type: null,
    secret: 'ThisIsNotSecret',

    redis: {
      host: '',
      port: ''
    }
  },

  organization: 'My Company Here',

  /**
   * GPG key to use when signing APT and YUM releases
   *
   * Requires to be unlocked (no password) and have both the private and
   * public key.
   */
  gpgSigningKey: `
-----BEGIN PGP PUBLIC KEY BLOCK-----

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
XmGGAN+pmaFeRcrPMjWkC24xrH2K
=NGmG
-----END PGP PUBLIC KEY BLOCK-----
-----BEGIN PGP PRIVATE KEY BLOCK-----

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
=oMAp
-----END PGP PRIVATE KEY BLOCK-----
`, 

  /**
   * The default percentage rollout for new releases.  The first release for
   * any channel will always be 100% but all future releases will have a
   * default rollout value of this setting
   */
  defaultRollout: 0
};
