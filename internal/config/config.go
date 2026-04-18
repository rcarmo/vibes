package config

import (
	"github.com/caarlos0/env/v11"
)

// Config holds all application configuration, loaded from environment variables.
// Field names match the Python vibes VIBES_* env vars for compatibility.
type Config struct {
	// Server
	Host  string `env:"VIBES_HOST" envDefault:"0.0.0.0"`
	Port  int    `env:"VIBES_PORT" envDefault:"8080"`
	Debug bool   `env:"VIBES_DEBUG" envDefault:"false"`

	// Database
	DBPath string `env:"VIBES_DB_PATH" envDefault:"database/vibes.db"`

	// Agent
	DefaultAgent string `env:"VIBES_DEFAULT_AGENT" envDefault:"acp"`
	AgentName    string `env:"VIBES_AGENT_NAME"`

	// ACP
	ACPAgent    string `env:"VIBES_ACP_AGENT" envDefault:"copilot --acp"`
	ACPDebug    bool   `env:"VIBES_ACP_DEBUG" envDefault:"false"`
	ACPThrottle int    `env:"VIBES_ACP_THROTTLE_RPS" envDefault:"0"`

	// Pi
	PiAgent              string `env:"VIBES_PI_AGENT"`
	PiEnabled            bool   `env:"VIBES_PI_ENABLED" envDefault:"false"`
	PiRestartOnDisconnect bool  `env:"VIBES_PI_RESTART_ON_DISCONNECT" envDefault:"false"`

	// Permissions
	PermissionTimeout     int  `env:"VIBES_PERMISSION_TIMEOUT" envDefault:"30"`
	PermissionAutoApprove bool `env:"VIBES_PERMISSION_AUTO_APPROVE" envDefault:"false"`

	// Disconnect behavior
	DisconnectTimeout int `env:"VIBES_DISCONNECT_TIMEOUT" envDefault:"300"`

	// Custom endpoints config
	ConfigPath string `env:"VIBES_CONFIG_PATH" envDefault:"config/endpoints.json"`

	// Extensions
	ExtensionsDir string `env:"VIBES_EXTENSIONS_DIR" envDefault:"extensions"`
}

// Load reads configuration from environment variables.
func Load() (*Config, error) {
	cfg := &Config{}
	if err := env.Parse(cfg); err != nil {
		return nil, err
	}

	// Auto-enable Pi if default agent is pi
	if cfg.DefaultAgent == "pi" {
		cfg.PiEnabled = true
	}

	return cfg, nil
}
