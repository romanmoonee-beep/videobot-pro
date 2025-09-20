ALTER TABLE users ADD COLUMN is_active BOOLEAN NOT NULL DEFAULT true;
CREATE INDEX idx_users_is_active ON users(is_active);
UPDATE users SET is_active = true WHERE is_active IS NULL;