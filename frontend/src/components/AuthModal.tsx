import { useState } from 'react';
import { register, login, type AuthResult } from '../api';

interface AuthModalProps {
  isOpen: boolean;
  onClose: () => void;
  onSuccess: () => void;
}

export function AuthModal({ isOpen, onClose, onSuccess }: AuthModalProps) {
  const [mode, setMode] = useState<'login' | 'register'>('login');
  const [phone, setPhone] = useState('');
  const [password, setPassword] = useState('');
  const [name, setName] = useState('');
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError('');
    setLoading(true);
    try {
      let result: AuthResult;
      if (mode === 'register') {
        result = await register(phone, password, name);
      } else {
        result = await login(phone, password);
      }
      if (result.success) {
        onSuccess();
        onClose();
        setPhone('');
        setPassword('');
        setName('');
      } else {
        setError(result.error || 'Ошибка');
      }
    } catch {
      setError('Ошибка сети');
    } finally {
      setLoading(false);
    }
  };

  if (!isOpen) return null;

  return (
    <div
      className="cart-modal active"
      onClick={(e) => e.target === e.currentTarget && onClose()}
      role="dialog"
      aria-modal="true"
      aria-label="Вход / Регистрация"
    >
      <div className="cart-panel auth-modal-panel" onClick={(e) => e.stopPropagation()}>
        <div className="cart-header">
          <div className="cart-title">{mode === 'login' ? 'Вход' : 'Регистрация'}</div>
          <button type="button" className="cart-close" onClick={onClose}>
            ×
          </button>
        </div>
        <form onSubmit={handleSubmit} className="auth-form">
          <div className="cart-contacts">
            <label htmlFor="auth-phone">Телефон *</label>
            <input
              id="auth-phone"
              type="tel"
              className="cart-comment-input"
              placeholder="+7 (999) 123-45-67"
              value={phone}
              onChange={(e) => setPhone(e.target.value)}
              required
            />
            {mode === 'register' && (
              <>
                <label htmlFor="auth-name">Имя</label>
                <input
                  id="auth-name"
                  type="text"
                  className="cart-comment-input"
                  placeholder="Как к вам обращаться"
                  value={name}
                  onChange={(e) => setName(e.target.value)}
                />
              </>
            )}
            <label htmlFor="auth-password">Пароль *</label>
            <input
              id="auth-password"
              type="password"
              className="cart-comment-input"
              placeholder={mode === 'register' ? 'Не менее 8 символов' : 'Пароль'}
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              required
              minLength={mode === 'register' ? 8 : undefined}
            />
          </div>
          {error && <div className="auth-error">{error}</div>}
          <button type="submit" className="btn-primary" disabled={loading}>
            {loading ? '...' : mode === 'login' ? 'Войти' : 'Зарегистрироваться'}
          </button>
        </form>
        <div className="auth-switch">
          <button
            type="button"
            className="auth-switch-btn"
            onClick={() => {
              setMode(mode === 'login' ? 'register' : 'login');
              setError('');
            }}
          >
            {mode === 'login' ? 'Нет аккаунта? Зарегистрироваться' : 'Уже есть аккаунт? Войти'}
          </button>
        </div>
      </div>
    </div>
  );
}
