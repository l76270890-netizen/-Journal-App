import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import {
  Archive, ArrowLeft, ArrowRight, Bell, BookOpen, CalendarDays, Check, ChevronDown,
  ChevronLeft, ChevronRight, CircleHelp, Clock3, Cloud, Command, Compass, Feather,
  Flame, Heart, Home, Leaf, LockKeyhole, LogOut, Menu, MoreHorizontal, Plus,
  Search, Settings, ShieldCheck, Smile, Sparkles, Tag, Trash2, TrendingUp, X,
} from 'lucide-react';
import { authenticate as authenticateApi, createNote, deleteAppLock, deleteNote, getAppLock, getNotes, setAppLock as setAppLockApi, updateNote, updateProfile, verifyAppLock } from './api';
import './lock.css';

const PHOTO = {
  mountain: 'https://images.unsplash.com/photo-1464822759023-fed622ff2c3b?auto=format&fit=crop&w=900&q=85',
  coffee: 'https://images.unsplash.com/photo-1445116572660-236099ec97a0?auto=format&fit=crop&w=700&q=85',
  plant: 'https://images.unsplash.com/photo-1497250681960-ef046c08a56e?auto=format&fit=crop&w=700&q=85',
  coast: 'https://images.unsplash.com/photo-1473116763249-2faaef81ccda?auto=format&fit=crop&w=800&q=85',
  city: 'https://images.unsplash.com/photo-1519608487953-e999c86e7455?auto=format&fit=crop&w=800&q=85',
  woods: 'https://images.unsplash.com/photo-1448375240586-882707db888b?auto=format&fit=crop&w=800&q=85',
};

const MOODS = [
  { name: 'Happy', face: '☀️', color: '#e5b34d' }, { name: 'Calm', face: '☻', color: '#668b69' },
  { name: 'Grateful', face: '♡', color: '#8aa98a' }, { name: 'Sad', face: '☹', color: '#8297b5' },
  { name: 'Angry', face: '⌁', color: '#c97d70' },
];

const seedEntries = [
  { id: 'e1', title: 'A quiet morning', body: 'Today started slow, and that was a good thing. I made time for myself, enjoyed a peaceful morning with a cup of coffee, and watched the light move across the room.\n\nI am grateful for the little things — a warm cup, a deep breath, a moment to begin again.', mood: 'Calm', tags: ['#gratitude', '#life', '#mindset'], date: '2025-07-15T10:24:00', image: PHOTO.mountain, favorite: true, archived: false },
  { id: 'e2', title: 'Small wins matter', body: 'I finished my project today! It wasn’t easy, but I’m proud of how far I’ve come. Progress, not perfection.', mood: 'Happy', tags: ['#growth', '#work'], date: '2025-07-13T15:10:00', image: PHOTO.coffee, favorite: true, archived: false },
  { id: 'e3', title: 'Things I’m grateful for', body: 'Good friends, good health, and new opportunities. Life is really full when you take a moment to notice.', mood: 'Grateful', tags: ['#gratitude', '#people'], date: '2025-07-11T09:40:00', image: PHOTO.plant, favorite: true, archived: false },
  { id: 'e4', title: 'Overcoming a tough day', body: 'It was a hard day, but I got through it. I’m learning that it is okay to have bad days. Tomorrow is a new day.', mood: 'Sad', tags: ['#selfcare', '#mindset'], date: '2025-07-09T19:20:00', image: PHOTO.city, favorite: false, archived: false },
  { id: 'e5', title: 'A walk by the water', body: 'The air felt softer near the coast. I came home with a clearer head and a few thoughts worth holding onto.', mood: 'Calm', tags: ['#life', '#selfcare'], date: '2025-07-06T17:05:00', image: PHOTO.coast, favorite: false, archived: false },
  { id: 'e6', title: 'Finding my way back', body: 'Some days ask us to be patient with ourselves. I am trying to meet this season with a little more kindness.', mood: 'Grateful', tags: ['#growth', '#mindset'], date: '2025-07-03T12:32:00', image: PHOTO.woods, favorite: false, archived: false },
];

const NAV = [
  { id: 'home', label: 'Home', Icon: Home }, { id: 'journal', label: 'Journal', Icon: BookOpen },
  { id: 'favorites', label: 'Favorites', Icon: Heart }, { id: 'calendar', label: 'Calendar', Icon: CalendarDays },
  { id: 'tags', label: 'Tags', Icon: Tag }, { id: 'archive', label: 'Archive', Icon: Archive },
];

const dateLabel = (date, opts = { month: 'short', day: 'numeric', year: 'numeric' }) => new Date(date).toLocaleDateString('en-US', opts);
const timeLabel = (date) => new Date(date).toLocaleTimeString('en-US', { hour: 'numeric', minute: '2-digit' });
const storageKey = (key, user) => `luma:${user?.email || 'guest'}:${key}`;
const readStore = (key, fallback, user) => { try { return JSON.parse(localStorage.getItem(storageKey(key, user))) ?? fallback; } catch { return fallback; } };

function Brand({ small = false }) {
  return <div className={`brand ${small ? 'brand-small' : ''}`}><span className="brand-mark"><Leaf size={25} strokeWidth={1.65} /></span><span><b>LUMA JOURNAL</b>{!small && <small>Better thoughts. A brighter you.</small>}</span></div>;
}

function MoodPill({ mood }) {
  const item = MOODS.find((m) => m.name === mood) || MOODS[1];
  return <span className={`mood-pill mood-${item.name.toLowerCase()}`}><i>{item.face}</i>{item.name}</span>;
}

function EntryCard({ entry, onOpen, onFavorite, compact = false }) {
  return <article className={`entry-card ${compact ? 'entry-card-compact' : ''}`} onClick={() => onOpen(entry)}>
    {entry.image && <img className="entry-thumb" src={entry.image} alt="" />}
    <div className="entry-card-copy"><div className="entry-card-top"><h3>{entry.title || 'Untitled entry'}</h3><span className="entry-date">{dateLabel(entry.date, { month: 'short', day: 'numeric' })}</span></div>
      <p>{entry.body || 'A new beginning.'}</p><div className="entry-meta"><MoodPill mood={entry.mood} />{entry.tags.slice(0, 2).map((tag) => <span key={tag} className="tag-chip">{tag}</span>)}</div>
    </div><button className={`icon-btn favorite-button ${entry.favorite ? 'is-favorite' : ''}`} aria-label={entry.favorite ? 'Remove from favorites' : 'Add to favorites'} onClick={(e) => { e.stopPropagation(); onFavorite(entry.id); }}><Heart size={16} fill={entry.favorite ? 'currentColor' : 'none'} /></button>
  </article>;
}

function CalendarWidget({ entries, onSelectDate, large = false }) {
  const [month, setMonth] = useState(new Date(2025, 6, 1));
  const first = new Date(month.getFullYear(), month.getMonth(), 1);
  const start = (first.getDay() + 6) % 7;
  const days = new Date(month.getFullYear(), month.getMonth() + 1, 0).getDate();
  const hasEntry = new Set(entries.map((entry) => new Date(entry.date).toDateString()));
  return <div className={`calendar-widget ${large ? 'calendar-widget-large' : ''}`}>
    <div className="calendar-title"><span>{month.toLocaleDateString('en-US', { month: 'long', year: 'numeric' })}</span><div><button className="icon-btn" aria-label="Previous month" onClick={() => setMonth(new Date(month.getFullYear(), month.getMonth() - 1, 1))}><ChevronLeft size={16} /></button><button className="icon-btn" aria-label="Next month" onClick={() => setMonth(new Date(month.getFullYear(), month.getMonth() + 1, 1))}><ChevronRight size={16} /></button></div></div>
    <div className="calendar-grid calendar-weekdays">{['Mo', 'Tu', 'We', 'Th', 'Fr', 'Sa', 'Su'].map((d) => <span key={d}>{d}</span>)}</div>
    <div className="calendar-grid">{Array.from({ length: start }, (_, i) => <span className="calendar-blank" key={`b${i}`} />)}{Array.from({ length: days }, (_, i) => { const date = new Date(month.getFullYear(), month.getMonth(), i + 1); const active = hasEntry.has(date.toDateString()); return <button key={i} className={`calendar-day ${active ? 'has-entry' : ''} ${i + 1 === 15 && month.getMonth() === 6 ? 'is-today' : ''}`} onClick={() => onSelectDate?.(date)}>{i + 1}{active && <i />}</button>; })}</div>
  </div>;
}

function AuthPage({ onAuth, onDemo }) {
  const [mode, setMode] = useState('login'); const [name, setName] = useState(''); const [email, setEmail] = useState(''); const [password, setPassword] = useState(''); const [error, setError] = useState(''); const [submitting, setSubmitting] = useState(false);
  const submit = async (e) => { e.preventDefault(); setError(''); if (!email.trim() || !password) { setError('Add your email and password to continue.'); return; } if (mode === 'signup' && !name.trim()) { setError('What should we call you?'); return; } if (mode === 'signup' && password.length < 8) { setError('Use at least 8 characters for your password.'); return; } setSubmitting(true); try { await onAuth({ name, email, password, mode }); } catch (authError) { setError(authError.message); } finally { setSubmitting(false); } };
  return <main className="auth-page"><div className="auth-brand"><Brand /><div className="auth-brand-links"><span>Write</span><b>·</b><span>Reflect</span><b>·</b><span>Grow</span></div></div><section className="auth-shell"><div className="auth-story"><div className="story-copy"><span className="eyebrow"><Leaf size={14} /> YOUR SPACE TO BEGIN AGAIN</span><h1>A calmer mind<br />builds a brighter you.</h1><p>Make room for your thoughts. Find clarity in the everyday.</p><div className="story-note">“A little progress each day adds up to big results.”<Leaf size={16} /></div></div></div><div className="auth-form-wrap"><div className="auth-form-head"><span className="eyebrow">YOUR PERSONAL JOURNAL</span><h2>{mode === 'login' ? 'Welcome back.' : 'Create your account.'}</h2><p>{mode === 'login' ? 'A quiet space to pick up where you left off.' : 'A few little details, then you’re all set.'}</p></div><form onSubmit={submit} className="auth-form">{mode === 'signup' && <label>Your name<input value={name} onChange={(e) => setName(e.target.value)} placeholder="Alex Carter" autoComplete="name" /></label>}<label>Email address<input value={email} onChange={(e) => setEmail(e.target.value)} placeholder="you@example.com" type="email" autoComplete="email" /></label><label>Password<input value={password} onChange={(e) => setPassword(e.target.value)} placeholder="At least 8 characters" type="password" autoComplete={mode === 'login' ? 'current-password' : 'new-password'} /></label>{error && <p className="form-error">{error}</p>}<button className="btn btn-primary btn-wide" type="submit" disabled={submitting}>{submitting ? 'Please wait…' : mode === 'login' ? 'Log in' : 'Create account'}<ArrowRight size={16} /></button></form><p className="auth-switch">{mode === 'login' ? 'New to Luma?' : 'Already have an account?'} <button onClick={() => { setMode(mode === 'login' ? 'signup' : 'login'); setError(''); }}>{mode === 'login' ? 'Create an account' : 'Log in'}</button></p><button className="demo-link" onClick={onDemo}>Explore the journal first <ArrowRight size={14} /></button><div className="auth-assurance"><LockKeyhole size={14} /> Your journal stays private to your account</div></div></section><footer className="auth-footer"><span>© 2025 Luma Journal</span><span>Make space for what matters.</span></footer></main>;
}

function PatternInput({ value, onChange, label }) {
  const addDot = (dot) => {
    if (!value.includes(String(dot))) onChange(`${value}${dot}`);
  };
  return <div className="app-lock-pattern-wrap">
    <div className="app-lock-pattern" role="group" aria-label={label}>
      {Array.from({ length: 9 }, (_, dot) => <button
        key={dot}
        type="button"
        className={value.includes(String(dot)) ? 'selected' : ''}
        aria-label={`Pattern dot ${dot + 1}${value.includes(String(dot)) ? ', selected' : ''}`}
        aria-pressed={value.includes(String(dot))}
        onClick={() => addDot(dot)}
      ><span>{value.includes(String(dot)) ? value.indexOf(String(dot)) + 1 : ''}</span></button>)}
    </div>
    <button className="text-link app-lock-clear" type="button" onClick={() => onChange('')}>Clear pattern</button>
  </div>;
}

function AppLockSettings({ appLock, onConfigure, onDisable, isDemo }) {
  const [lockType, setLockType] = useState('pin');
  const [secret, setSecret] = useState('');
  const [confirmation, setConfirmation] = useState('');
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);

  const save = async (event) => {
    event.preventDefault();
    setError('');
    const valid = lockType === 'pin'
      ? /^\d{4,8}$/.test(secret)
      : /^[0-8]{4,9}$/.test(secret) && new Set(secret).size === secret.length;
    if (!valid) {
      setError(lockType === 'pin'
        ? 'Use a PIN with 4 to 8 digits.'
        : 'Connect at least 4 different dots in your pattern.');
      return;
    }
    if (secret !== confirmation) {
      setError('The two entries do not match.');
      return;
    }
    setBusy(true);
    try {
      await onConfigure(lockType, secret);
      setSecret('');
      setConfirmation('');
    } catch (saveError) {
      setError(saveError.message);
    } finally {
      setBusy(false);
    }
  };

  const disable = async () => {
    setError('');
    setBusy(true);
    try {
      await onDisable();
    } catch (disableError) {
      setError(disableError.message);
    } finally {
      setBusy(false);
    }
  };

  if (isDemo) return <div className="app-lock-explainer">
    <p>App lock is available for signed-in accounts. Sign in to save a PIN or pattern securely to your account.</p>
  </div>;

  return <div className="app-lock-settings">
    <div className="setting-row">
      <span><b>{appLock.enabled ? 'App lock is on' : 'App lock is off'}</b><small>Require a code when you reopen the app or after 5 minutes of inactivity.</small></span>
      <span className={`status-badge ${appLock.enabled ? '' : 'status-badge-off'}`}><i />{appLock.enabled ? `${appLock.lock_type === 'pin' ? 'PIN' : 'Pattern'} enabled` : 'Optional'}</span>
    </div>
    <p className="app-lock-disclaimer">This is a privacy screen for your signed-in session, not a replacement for your account password.</p>
    <form className="app-lock-form" onSubmit={save}>
      <div className="app-lock-type-choice" role="group" aria-label="Choose app lock type">
        <button type="button" className={lockType === 'pin' ? 'selected' : ''} onClick={() => { setLockType('pin'); setSecret(''); setConfirmation(''); setError(''); }}>PIN</button>
        <button type="button" className={lockType === 'pattern' ? 'selected' : ''} onClick={() => { setLockType('pattern'); setSecret(''); setConfirmation(''); setError(''); }}>Pattern</button>
      </div>
      {lockType === 'pin' ? <>
        <label className="settings-field">New 4–8 digit PIN<input type="password" inputMode="numeric" autoComplete="new-password" maxLength={8} value={secret} onChange={(event) => setSecret(event.target.value.replace(/\D/g, ''))} /></label>
        <label className="settings-field">Confirm PIN<input type="password" inputMode="numeric" autoComplete="new-password" maxLength={8} value={confirmation} onChange={(event) => setConfirmation(event.target.value.replace(/\D/g, ''))} /></label>
      </> : <>
        <div className="app-lock-pattern-field"><span>Draw a pattern using at least 4 dots</span><PatternInput value={secret} onChange={setSecret} label="Choose a pattern" /></div>
        <div className="app-lock-pattern-field"><span>Draw it again to confirm</span><PatternInput value={confirmation} onChange={setConfirmation} label="Confirm your pattern" /></div>
      </>}
      {error && <p className="form-error" role="alert">{error}</p>}
      <div className="app-lock-actions"><button className="btn btn-primary" type="submit" disabled={busy}>{busy ? 'Saving…' : appLock.enabled ? 'Update app lock' : 'Enable app lock'}</button>{appLock.enabled && <button className="btn btn-outline danger-outline" type="button" onClick={disable} disabled={busy}>Turn off</button>}</div>
    </form>
  </div>;
}

function AppLockScreen({ user, lockType, onUnlock, onLogout }) {
  const [secret, setSecret] = useState('');
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);
  const submit = async (event) => {
    event.preventDefault();
    setError('');
    setBusy(true);
    try {
      if (await onUnlock(lockType, secret)) {
        setSecret('');
      } else {
        setError('That code or pattern is not correct. Try again.');
        setSecret('');
      }
    } catch (unlockError) {
      setError(unlockError.message);
    } finally {
      setBusy(false);
    }
  };
  return <main className="app-lock-screen">
    <section className="app-lock-card">
      <Brand />
      <span className="app-lock-icon"><LockKeyhole size={22} /></span>
      <h1>Welcome back, {user.name?.split(' ')[0] || 'friend'}.</h1>
      <p>Unlock your journal to continue.</p>
      <form onSubmit={submit}>
        {lockType === 'pin'
          ? <label className="app-lock-pin">Enter your PIN<input type="password" inputMode="numeric" autoComplete="current-password" maxLength={8} value={secret} onChange={(event) => setSecret(event.target.value.replace(/\D/g, ''))} autoFocus /></label>
          : <div className="app-lock-pattern-field"><span>Draw your pattern</span><PatternInput value={secret} onChange={setSecret} label="Enter your pattern" /></div>}
        {error && <p className="form-error" role="alert">{error}</p>}
        <button className="btn btn-primary btn-wide" type="submit" disabled={busy}>{busy ? 'Checking…' : 'Unlock journal'}<ArrowRight size={16} /></button>
      </form>
      <button className="app-lock-logout" type="button" onClick={onLogout}>Sign out instead</button>
    </section>
  </main>;
}

function EntryEditor({ entry, onSave, onClose }) {
  const [title, setTitle] = useState(entry?.title || ''); const [body, setBody] = useState(entry?.body || ''); const [mood, setMood] = useState(entry?.mood || 'Calm'); const [tagsText, setTagsText] = useState(entry?.tags?.join(' ') || ''); const [saved, setSaved] = useState(false);
  const save = async () => { if (!title.trim() && !body.trim()) return; const tags = tagsText.split(/[\s,]+/).filter(Boolean).map((tag) => tag.startsWith('#') ? tag : `#${tag.replace(/^#/, '')}`); const succeeded = await onSave({ ...entry, id: entry?.id, title: title.trim() || 'Untitled entry', body: body.trim(), mood, tags, date: entry?.date || new Date().toISOString(), image: entry?.image || null, favorite: entry?.favorite || false, archived: entry?.archived || false }); if (succeeded) { setSaved(true); setTimeout(onClose, 450); } };
  return <div className="editor-overlay" onMouseDown={(e) => { if (e.target === e.currentTarget) onClose(); }}><section className="editor-modal"><header className="editor-header"><button className="icon-btn editor-close" onClick={onClose} aria-label="Close"><X size={19} /></button><div className="editor-heading"><span className="eyebrow">A MOMENT FOR YOU</span><h2>{entry ? 'Edit entry' : 'New entry'}</h2></div><button className="btn btn-primary btn-save" onClick={save}>{saved ? <Check size={16} /> : null}{saved ? 'Saved' : 'Save entry'}</button></header><div className="editor-content"><label className="title-field"><span>Title</span><input value={title} onChange={(e) => setTitle(e.target.value)} placeholder="A new beginning" autoFocus /></label><section className="mood-picker"><span className="field-label">How are you feeling?</span><div className="mood-options">{MOODS.map((item) => <button key={item.name} className={`mood-option ${mood === item.name ? 'selected' : ''}`} onClick={() => setMood(item.name)}><i style={{ color: item.color }}>{item.face}</i><span>{item.name}</span></button>)}</div></section><label className="body-field"><span className="field-label">Write your thoughts...</span><textarea value={body} onChange={(e) => setBody(e.target.value)} placeholder="Today I noticed..." /><div className="editor-tools"><button title="Bold"><b>B</b></button><button title="Italic"><i>I</i></button><span /><button title="Bulleted list">☷</button><button title="Add a link">↗</button><button title="Add an image">▧</button></div></label><label className="tags-field"><span className="field-label">Tags</span><div className="tag-input-wrap"><Tag size={15} /><input value={tagsText} onChange={(e) => setTagsText(e.target.value)} placeholder="#gratitude  #life  #mindset" /></div><small>Separate tags with spaces or commas</small></label><div className="editor-bottom"><span><Cloud size={15} /> Saved privately on this device</span><button className="btn btn-primary" onClick={save}>{saved ? 'Saved ✓' : 'Save entry'}</button></div></div></section></div>;
}

function App() {
  const [user, setUser] = useState(() => { try { const saved = JSON.parse(localStorage.getItem('luma:session')); return saved?.token || saved?.demo ? saved : null; } catch { return null; } });
  const [appLock, setAppLock] = useState({ enabled: false, lock_type: null });
  const [appLocked, setAppLocked] = useState(false);
  const [lockReady, setLockReady] = useState(false);
  const [lockError, setLockError] = useState('');
  const [lockRetry, setLockRetry] = useState(0);
  const [view, setView] = useState('home'); const [entries, setEntries] = useState([]); const [entriesLoading, setEntriesLoading] = useState(false); const [editor, setEditor] = useState(null); const [selected, setSelected] = useState(null);
  const [query, setQuery] = useState(''); const [moodFilter, setMoodFilter] = useState('All moods'); const [sort, setSort] = useState('Newest first'); const [tagFilter, setTagFilter] = useState(''); const [toast, setToast] = useState(''); const [menuOpen, setMenuOpen] = useState(false); const [profileOpen, setProfileOpen] = useState(false); const [mobileSearch, setMobileSearch] = useState(false); const [selectedDate, setSelectedDate] = useState(null);
  const searchInput = useRef(null);
  const lastActivity = useRef(Date.now());
  useEffect(() => {
    let cancelled = false;
    setLockReady(false);
    setLockError('');
    if (!user) {
      setAppLock({ enabled: false, lock_type: null });
      setAppLocked(false);
      setLockReady(true);
      return () => { cancelled = true; };
    }
    if (user.demo) {
      setAppLock({ enabled: false, lock_type: null });
      setAppLocked(false);
      setLockReady(true);
      return () => { cancelled = true; };
    }
    getAppLock(user.token)
      .then((status) => {
        if (cancelled) return;
        setAppLock(status);
        setAppLocked(status.enabled);
        setLockReady(true);
      })
      .catch((error) => {
        if (!cancelled) setLockError(error.message);
      });
    return () => { cancelled = true; };
  }, [user?.token, user?.demo, lockRetry]);

  const lockApp = useCallback(() => {
    setAppLocked(true);
    setEntries([]);
    setSelected(null);
    setEditor(null);
  }, []);

  useEffect(() => {
    if (!user) {
      setEntries([]);
      setEntriesLoading(false);
      return undefined;
    }
    if (!lockReady || appLocked) {
      setEntriesLoading(false);
      return undefined;
    }
    if (user.demo) {
      setEntries(readStore('entries', seedEntries, user));
      setEntriesLoading(false);
      return undefined;
    }

    let cancelled = false;
    setEntriesLoading(true);
    getNotes(user.token)
      .then((loadedEntries) => { if (!cancelled) setEntries(loadedEntries); })
      .catch((error) => {
        if (!cancelled) {
          setEntries([]);
          setToast(error.message);
        }
      })
      .finally(() => { if (!cancelled) setEntriesLoading(false); });
    return () => { cancelled = true; };
  }, [user?.token, user?.demo, lockReady, appLocked]);

  useEffect(() => {
    if (!user || user.demo || !lockReady || !appLock.enabled || appLocked) return undefined;
    let timer;
    const armIdleTimer = () => {
      lastActivity.current = Date.now();
      window.clearTimeout(timer);
      timer = window.setTimeout(lockApp, 5 * 60 * 1000);
    };
    const checkWhenVisible = () => {
      if (document.visibilityState === 'visible' && Date.now() - lastActivity.current >= 5 * 60 * 1000) {
        lockApp();
      }
    };
    const events = ['pointerdown', 'pointermove', 'keydown', 'scroll', 'touchstart'];
    events.forEach((eventName) => window.addEventListener(eventName, armIdleTimer, { passive: true }));
    document.addEventListener('visibilitychange', checkWhenVisible);
    armIdleTimer();
    return () => {
      window.clearTimeout(timer);
      events.forEach((eventName) => window.removeEventListener(eventName, armIdleTimer));
      document.removeEventListener('visibilitychange', checkWhenVisible);
    };
  }, [user?.token, user?.demo, lockReady, appLock.enabled, appLocked, lockApp]);
  useEffect(() => { if (user?.demo) localStorage.setItem(storageKey('entries', user), JSON.stringify(entries)); }, [entries, user]);
  useEffect(() => { window.scrollTo(0, 0); }, [view]);
  useEffect(() => { const handleShortcut = (event) => { if (!lockReady || appLocked) return; const editing = ['INPUT', 'TEXTAREA', 'SELECT'].includes(document.activeElement?.tagName) || document.activeElement?.isContentEditable; if ((event.metaKey || event.ctrlKey) && event.key.toLowerCase() === 'k') { event.preventDefault(); searchInput.current?.focus(); } else if (!editing && !event.metaKey && !event.ctrlKey && event.key.toLowerCase() === 'n') { event.preventDefault(); setEditor({}); } }; window.addEventListener('keydown', handleShortcut); return () => window.removeEventListener('keydown', handleShortcut); }, [lockReady, appLocked]);
  const activeEntries = entries.filter((entry) => !entry.archived);
  const filtered = useMemo(() => { let result = view === 'archive' ? entries.filter((entry) => entry.archived) : activeEntries; if (view === 'favorites') result = result.filter((entry) => entry.favorite); if (tagFilter) result = result.filter((entry) => entry.tags.includes(tagFilter)); if (moodFilter !== 'All moods') result = result.filter((entry) => entry.mood === moodFilter); if (selectedDate && ['journal', 'calendar'].includes(view)) result = result.filter((entry) => new Date(entry.date).toDateString() === selectedDate.toDateString()); const needle = query.trim().toLowerCase(); if (needle) result = result.filter((entry) => `${entry.title} ${entry.body} ${entry.tags.join(' ')}`.toLowerCase().includes(needle)); return [...result].sort((a, b) => sort === 'Oldest first' ? new Date(a.date) - new Date(b.date) : new Date(b.date) - new Date(a.date)); }, [entries, activeEntries, view, tagFilter, moodFilter, selectedDate, query, sort]);
  const notify = (message) => { setToast(message); setTimeout(() => setToast(''), 2500); };
  const authenticate = async (credentials) => {
    const authenticatedUser = await authenticateApi(credentials);
    localStorage.setItem('luma:session', JSON.stringify(authenticatedUser));
    setLockReady(false);
    setUser(authenticatedUser);
    setView('home');
  };
  const enterDemo = () => {
    const demoUser = { name: 'Alex Carter', email: 'alex@lumajournal.app', demo: true };
    localStorage.setItem('luma:session', JSON.stringify(demoUser));
    setUser(demoUser);
    setView('home');
  };
  const logout = () => { localStorage.removeItem('luma:session'); setUser(null); setView('home'); setSelected(null); setProfileOpen(false); };
  const saveEntry = async (entry) => {
    try {
      let savedEntry;
      if (user.demo) {
        savedEntry = { ...entry, id: entry.id || `e${Date.now()}` };
      } else {
        const { id, ...payload } = entry;
        savedEntry = id ? await updateNote(user.token, id, payload) : await createNote(user.token, payload);
      }
      setEntries((old) => [savedEntry, ...old.filter((item) => item.id !== savedEntry.id)]);
      setSelected(savedEntry);
      notify('Your thoughts have been saved.');
      return true;
    } catch (error) {
      notify(error.message);
      return false;
    }
  };
  const updateEntry = async (id, changes) => {
    const current = entries.find((entry) => entry.id === id);
    if (!current) return false;
    const updatedEntry = { ...current, ...changes };
    try {
      const savedEntry = user.demo ? updatedEntry : await updateNote(user.token, id, updatedEntry);
      setEntries((old) => old.map((entry) => entry.id === id ? savedEntry : entry));
      setSelected((old) => old?.id === id ? savedEntry : old);
      return true;
    } catch (error) {
      notify(error.message);
      return false;
    }
  };
  const toggleFavorite = (id) => {
    const entry = entries.find((item) => item.id === id);
    if (entry) updateEntry(id, { favorite: !entry.favorite });
  };
  const archiveEntry = (id) => updateEntry(id, { archived: true });
  const removeEntry = async (id) => {
    try {
      if (!user.demo) await deleteNote(user.token, id);
      setEntries((old) => old.filter((entry) => entry.id !== id));
      notify('Entry deleted.');
      go('journal');
    } catch (error) {
      notify(error.message);
    }
  };
  const saveUserName = async (name) => {
    const trimmedName = name.trim();
    if (!trimmedName) return;
    try {
      const profile = user.demo ? { name: trimmedName } : await updateProfile(user.token, trimmedName);
      const updatedUser = { ...user, ...profile };
      setUser(updatedUser);
      localStorage.setItem('luma:session', JSON.stringify(updatedUser));
      notify('Profile updated.');
    } catch (error) {
      notify(error.message);
    }
  };
  const configureAppLock = async (lockType, secret) => {
    const status = await setAppLockApi(user.token, lockType, secret);
    setAppLock(status);
    notify('App lock enabled.');
  };
  const disableAppLock = async () => {
    await deleteAppLock(user.token);
    setAppLock({ enabled: false, lock_type: null });
    notify('App lock turned off.');
  };
  const unlockApp = async (lockType, secret) => {
    const verified = await verifyAppLock(user.token, lockType, secret);
    if (verified) {
      lastActivity.current = Date.now();
      setAppLocked(false);
    }
    return verified;
  };
  const go = (id) => { setView(id); setTagFilter(''); setSelectedDate(null); setQuery(''); setSelected(null); setMenuOpen(false); };
  const uniqueTags = [...new Set(activeEntries.flatMap((entry) => entry.tags))].sort();
  const latest = [...activeEntries].sort((a, b) => new Date(b.date) - new Date(a.date));
  const greeting = user?.name?.split(' ')[0] || 'friend';
  const dateToday = new Date().toLocaleDateString('en-US', { weekday: 'long', month: 'long', day: 'numeric', year: 'numeric' });

  if (!user) return <AuthPage onAuth={authenticate} onDemo={enterDemo} />;
  if (!lockReady) return <main className="app-lock-screen"><section className="app-lock-card"><Brand /><span className="app-lock-icon"><LockKeyhole size={22} /></span><h1>{lockError ? 'App lock unavailable' : 'Checking your app lock…'}</h1>{lockError && <><p>{lockError}</p><button className="btn btn-primary btn-wide" onClick={() => { setLockError(''); setLockRetry((retry) => retry + 1); }}>Try again</button><button className="app-lock-logout" onClick={logout}>Sign out</button></>}</section></main>;
  if (appLocked && appLock.enabled) return <AppLockScreen user={user} lockType={appLock.lock_type} onUnlock={unlockApp} onLogout={logout} />;
  const viewTitles = { journal: 'My journal', favorites: 'Favorites', archive: 'Archive', tags: 'Your tags', calendar: 'Calendar', settings: 'Settings' };
  const heading = viewTitles[view] || (view === 'home' ? 'Your journal, at a glance' : 'Your journal');
  const openEntry = (entry) => { setSelected(entry); setView('detail'); };
  const viewEntryById = (id) => activeEntries.find((item) => item.id === id);
  return <div className="app-shell">
    <aside className={`sidebar ${menuOpen ? 'sidebar-open' : ''}`}><div className="sidebar-top"><Brand small /><button className="icon-btn sidebar-close" onClick={() => setMenuOpen(false)} aria-label="Close navigation"><X size={19} /></button></div><button className="btn btn-primary new-entry-button" onClick={() => setEditor({})}><Plus size={17} /> New entry <span className="shortcut">N</span></button><nav className="side-nav" aria-label="Main navigation">{NAV.map(({ id, label, Icon }) => <button key={id} className={`nav-item ${view === id ? 'active' : ''}`} onClick={() => go(id)}><Icon size={18} strokeWidth={1.8} /><span>{label}</span>{id === 'favorites' && <span className="nav-count">{activeEntries.filter((entry) => entry.favorite).length}</span>}</button>)}</nav><div className="sidebar-grow" /><div className="sidebar-quote"><span className="quote-mark">“</span><p>A little progress<br />each day adds up<br />to big results.</p><Leaf size={17} /></div><button className={`nav-item settings-link ${view === 'settings' ? 'active' : ''}`} onClick={() => go('settings')}><Settings size={18} /><span>Settings</span></button><button className="sidebar-profile" onClick={() => setProfileOpen(!profileOpen)}><div className="avatar">{greeting[0]?.toUpperCase()}</div><span><b>{user.name}</b><small>Personal journal</small></span><MoreHorizontal size={19} /></button></aside>
    {menuOpen && <button className="sidebar-scrim" aria-label="Close menu" onClick={() => setMenuOpen(false)} />}
    <main className="main-area"><header className="topbar"><button className="icon-btn mobile-menu" onClick={() => setMenuOpen(true)} aria-label="Open navigation"><Menu size={20} /></button><div className={`search-box ${mobileSearch ? 'search-open' : ''}`}><Search size={17} /><input ref={searchInput} value={query} onChange={(e) => { setQuery(e.target.value); if (e.target.value && view !== 'journal') { setView('journal'); setSelected(null); } }} placeholder="Search your journal..." /><kbd><Command size={11} /> K</kbd>{mobileSearch && <button className="icon-btn search-close" onClick={() => { setMobileSearch(false); setQuery(''); }}><X size={16} /></button>}</div><div className="topbar-actions"><button className="icon-btn mobile-search-button" aria-label="Search" onClick={() => setMobileSearch(true)}><Search size={19} /></button><button className="icon-btn notification-button" onClick={() => notify('You’re all caught up.')} aria-label="Notifications"><Bell size={18} /><i /></button><div className="profile-anchor"><button className="profile-button" onClick={() => setProfileOpen(!profileOpen)}><div className="avatar avatar-small">{greeting[0]?.toUpperCase()}</div><span>{user.name}</span><ChevronDown size={14} /></button>{profileOpen && <div className="profile-menu"><div className="profile-menu-user"><b>{user.name}</b><small>{user.email}</small></div><button onClick={() => { go('settings'); setProfileOpen(false); }}><Settings size={15} /> Account settings</button><button onClick={logout}><LogOut size={15} /> Log out</button></div>}</div></div></header>
      <div className="page-content">
        {entriesLoading && <p role="status">Loading your journal…</p>}
        {view === 'home' && <><div className="welcome-row"><div><span className="eyebrow">{dateToday.toUpperCase()}</span><h1>Good afternoon, {greeting}<span className="wave">✳</span></h1><p className="page-subtitle">Take a moment for yourself. How are you feeling today?</p></div><button className="btn btn-primary welcome-new" onClick={() => setEditor({})}><Plus size={17} /> New entry</button></div>
          <div className="dashboard-grid"><section className="dashboard-main"><div className="stats-row"><div className="stat-card"><span className="stat-icon flame-icon"><Flame size={19} /></span><div><strong>{Math.min(activeEntries.length + 1, 12)}</strong><span>day streak</span></div><span className="stat-caption">You’re showing up</span></div><div className="stat-card"><span className="stat-icon mood-stat-icon"><Smile size={20} /></span><div><strong>Calm</strong><span>most common mood</span></div><span className="stat-caption">Over the last 7 days</span></div><div className="stat-card stat-card-progress"><span className="progress-ring">{Math.min(activeEntries.length, 7)}<small>/7</small></span><div><strong>Your week</strong><span>journal goal</span></div></div></div>
            <div className="section-heading"><div><h2>Recent entries</h2><p>Your thoughts, lately</p></div><button className="text-link" onClick={() => go('journal')}>View all <ArrowRight size={15} /></button></div>
            <div className="entry-list">{latest.slice(0, 4).map((entry) => <EntryCard key={entry.id} entry={entry} onOpen={openEntry} onFavorite={toggleFavorite} />)}{latest.length === 0 && <EmptyState onCreate={() => setEditor({})} />}</div>
            <div className="reflection-banner"><div className="reflection-sun">☼</div><div><span className="eyebrow">A GENTLE REMINDER</span><p>“You don’t have to have it all figured out to take the next step.”</p></div><Leaf size={28} /></div>
          </section><aside className="dashboard-rail"><div className="rail-card calendar-card"><div className="section-heading section-heading-tight"><div><h2>Your calendar</h2><p>Little moments add up</p></div><button className="icon-btn" onClick={() => go('calendar')} aria-label="Open calendar"><ArrowRight size={16} /></button></div><CalendarWidget entries={activeEntries} onSelectDate={(date) => { setSelectedDate(date); setView('journal'); }} /></div><div className="rail-card mood-card"><div className="section-heading section-heading-tight"><div><h2>Mood check-in</h2><p>A feeling for today</p></div><span className="today-soft">Today</span></div><div className="weekly-moods">{['M', 'T', 'W', 'T', 'F', 'S', 'S'].map((day, i) => <div key={`${day}${i}`}><span className={`mood-dot ${['mood-green', 'mood-green', 'mood-yellow', 'mood-green', 'mood-blue', 'mood-gray', 'mood-gray'][i]}`}>{['☻', '☻', '☼', '♡', '☹', '·', '·'][i]}</span><small>{day}</small></div>)}</div><button className="mood-reflect" onClick={() => setEditor({ mood: 'Calm' })}><span className="reflect-leaf"><Leaf size={19} /></span><span><b>How are you feeling?</b><small>Check in with yourself</small></span><ChevronRight size={17} /></button></div><div className="rail-card tags-card"><div className="section-heading section-heading-tight"><div><h2>Your tags</h2><p>Find a familiar thought</p></div><button className="text-link" onClick={() => go('tags')}>All <ArrowRight size={14} /></button></div><div className="quick-tags">{uniqueTags.slice(0, 6).map((tag) => <button key={tag} className="tag-chip" onClick={() => { setTagFilter(tag); setView('journal'); }}>{tag}</button>)}</div></div><div className="insight-note"><Sparkles size={17} /><p>Every page you write is a little more understanding of yourself.</p></div></aside></div></>}
        {['journal', 'favorites', 'archive'].includes(view) && <><div className="page-heading"><div><span className="eyebrow">A PLACE FOR YOUR THOUGHTS</span><h1>{heading}</h1><p className="page-subtitle">{view === 'archive' ? 'A quiet place for entries you’ve tucked away.' : view === 'favorites' ? 'The moments you want to come back to.' : 'Every thought, feeling, and little moment.'}</p></div><button className="btn btn-primary welcome-new" onClick={() => setEditor({})}><Plus size={17} /> New entry</button></div><div className="list-controls"><div className="filter-select-wrap"><Smile size={15} /><select value={moodFilter} onChange={(e) => setMoodFilter(e.target.value)}><option>All moods</option>{MOODS.map((mood) => <option key={mood.name}>{mood.name}</option>)}</select><ChevronDown size={14} /></div><div className="filter-select-wrap"><Clock3 size={15} /><select value={sort} onChange={(e) => setSort(e.target.value)}><option>Newest first</option><option>Oldest first</option></select><ChevronDown size={14} /></div>{selectedDate && <button className="filter-clear" onClick={() => setSelectedDate(null)}>{dateLabel(selectedDate)} <X size={14} /></button>}{tagFilter && <button className="filter-clear" onClick={() => setTagFilter('')}>{tagFilter} <X size={14} /></button>}<span className="results-count">{filtered.length} {filtered.length === 1 ? 'entry' : 'entries'}</span></div><div className="full-entry-list">{filtered.map((entry) => <EntryCard key={entry.id} entry={entry} onOpen={openEntry} onFavorite={toggleFavorite} />)}{filtered.length === 0 && <EmptyState onCreate={() => setEditor({})} message={query ? 'No entries match your search.' : 'Nothing here just yet.'} />}</div></>}
        {view === 'calendar' && <><div className="page-heading"><div><span className="eyebrow">YOUR DAYS, IN LITTLE MOMENTS</span><h1>Calendar</h1><p className="page-subtitle">See how your days have been unfolding.</p></div><button className="btn btn-primary welcome-new" onClick={() => setEditor({})}><Plus size={17} /> New entry</button></div><div className="calendar-page-grid"><div className="rail-card calendar-main-card"><CalendarWidget entries={activeEntries} large onSelectDate={(date) => { setSelectedDate(date); setView('journal'); }} /><p className="calendar-hint"><span className="calendar-key-dot" /> A little dot means you wrote something that day</p></div><div className="rail-card calendar-day-card"><span className="eyebrow">RECENT MOMENTS</span><h2>Your journal days</h2>{latest.slice(0, 4).map((entry) => <button className="calendar-entry-link" key={entry.id} onClick={() => openEntry(entry)}><span className="calendar-entry-date">{new Date(entry.date).getDate()}<small>{new Date(entry.date).toLocaleDateString('en-US', { month: 'short' })}</small></span><span><b>{entry.title}</b><small>{dateLabel(entry.date)} · {entry.mood}</small></span><ChevronRight size={16} /></button>)}</div></div></>}
        {view === 'tags' && <><div className="page-heading"><div><span className="eyebrow">FOLLOW A THREAD</span><h1>Your tags</h1><p className="page-subtitle">Little themes that make your journal yours.</p></div><button className="btn btn-primary welcome-new" onClick={() => setEditor({})}><Plus size={17} /> New entry</button></div><div className="tag-overview-grid">{uniqueTags.map((tag) => { const count = activeEntries.filter((entry) => entry.tags.includes(tag)).length; return <button className="tag-overview-card" key={tag} onClick={() => { setTagFilter(tag); setView('journal'); }}><span className="tag-card-icon"><Tag size={17} /></span><b>{tag}</b><small>{count} {count === 1 ? 'entry' : 'entries'}</small><ArrowRight size={16} /></button>; })}</div></>}
        {view === 'detail' && selected && <><button className="back-link" onClick={() => go('journal')}><ArrowLeft size={16} /> Back to journal</button><article className="detail-card"><div className="detail-cover" style={{ backgroundImage: `url(${selected.image || PHOTO.plant})` }}><button className="detail-back-mobile icon-btn" onClick={() => go('journal')}><ArrowLeft size={17} /></button></div><div className="detail-content"><div className="detail-topline"><span className="eyebrow">A MOMENT IN YOUR JOURNAL</span><div className="detail-actions"><button className="btn btn-outline" onClick={() => setEditor(selected)}>Edit entry</button><button className={`icon-btn ${selected.favorite ? 'is-favorite' : ''}`} aria-label="Toggle favorite" onClick={() => toggleFavorite(selected.id)}><Heart size={18} fill={selected.favorite ? 'currentColor' : 'none'} /></button><button className="icon-btn" aria-label="Archive entry" onClick={async () => { if (await archiveEntry(selected.id)) { notify('Entry moved to your archive.'); go('archive'); } }}><Archive size={18} /></button><button className="icon-btn danger-icon" aria-label="Delete entry" onClick={() => removeEntry(selected.id)}><Trash2 size={17} /></button></div></div><h1>{selected.title}</h1><div className="detail-meta"><span>{dateLabel(selected.date, { weekday: 'long', month: 'long', day: 'numeric', year: 'numeric' })}</span><span>·</span><span>{timeLabel(selected.date)}</span><MoodPill mood={selected.mood} /></div><div className="detail-divider" /><p className="detail-body">{selected.body}</p><div className="detail-tags">{selected.tags.map((tag) => <button className="tag-chip" key={tag} onClick={() => { setTagFilter(tag); setView('journal'); }}>{tag}</button>)}</div><div className="detail-footer"><Leaf size={16} /><span>Thank you for showing up for yourself today.</span></div></div></article></>}
        {view === 'settings' && <>
          <div className="page-heading"><div><span className="eyebrow">MAKE IT YOURS</span><h1>Settings</h1><p className="page-subtitle">Your account, your space, your pace.</p></div></div>
          <div className="settings-layout">
            <aside className="settings-nav">{[['Profile', 'profile'], ['Account', 'account'], ['Privacy & security', 'privacy'], ['Appearance', 'appearance']].map(([item]) => <button key={item} className="settings-nav-item" onClick={() => document.getElementById(item.toLowerCase().replaceAll(' ', '-').replace('&-', ''))?.scrollIntoView({ behavior: 'smooth' })}>{item}<ChevronRight size={15} /></button>)}</aside>
            <div className="settings-sections">
              <section className="settings-card" id="profile"><div className="settings-card-heading"><div><h2>Your profile</h2><p>A little about the person behind the pages.</p></div><div className="avatar avatar-large">{greeting[0]?.toUpperCase()}</div></div><label className="settings-field">Name<input defaultValue={user.name} onBlur={(e) => saveUserName(e.target.value)} /></label><label className="settings-field">Email address<input defaultValue={user.email} disabled /></label><div className="settings-card-footer"><span>Personal journal</span><button className="btn btn-outline" onClick={() => notify('Your profile is up to date.')}>Save changes</button></div></section>
              <section className="settings-card" id="account"><div className="settings-card-heading"><div><h2>Account</h2><p>Manage your Luma Journal session.</p></div><ShieldCheck size={21} className="settings-card-icon" /></div><div className="setting-row"><span><b>Journal storage</b><small>{user.demo ? 'Demo entries are saved in this browser.' : 'Your entries are saved to your account.'}</small></span><span className="status-badge"><i /> {user.demo ? 'On this device' : 'Account storage'}</span></div><div className="setting-row"><span><b>Sign-in email</b><small>{user.email}</small></span><LockKeyhole size={17} /></div><div className="settings-card-footer"><span>Need a fresh start?</span><button className="btn btn-outline danger-outline" onClick={logout}><LogOut size={15} /> Log out</button></div></section>
              <section className="settings-card" id="privacy-security"><div className="settings-card-heading"><div><h2>Privacy & security</h2><p>Your journal belongs to you.</p></div><LockKeyhole size={20} className="settings-card-icon" /></div><div className="privacy-note"><ShieldCheck size={18} /><div><b>Private by nature</b><p>{user.demo ? 'Demo entries are stored in this browser.' : 'Your journal entries are stored with your account and protected by sign-in.'} This app does not currently include password recovery.</p></div></div><div className="app-lock-divider" /><div className="app-lock-heading"><div><b>Optional app lock</b><p>Choose a PIN or a pattern to lock this account when reopening the app or after inactivity.</p></div><LockKeyhole size={17} /></div><AppLockSettings appLock={appLock} onConfigure={configureAppLock} onDisable={disableAppLock} isDemo={user.demo} /></section>
              <section className="settings-card" id="appearance"><div className="settings-card-heading"><div><h2>Appearance</h2><p>A softer space for your everyday.</p></div><Sparkles size={20} className="settings-card-icon" /></div><div className="appearance-choice"><span className="appearance-swatch" /><span><b>Calm & considered</b><small>Warm paper, soft greens, and plenty of breathing room.</small></span><Check size={17} /></div></section>
            </div>
          </div>
        </>}
      </div><footer className="main-footer"><Brand small /><span>Make space for what matters. <Leaf size={13} /></span></footer></main>
    {profileOpen && <button aria-label="Close profile menu" className="click-catcher" onClick={() => setProfileOpen(false)} />}
    <nav className="mobile-tabbar">{[{ id: 'home', label: 'Home', Icon: Home }, { id: 'journal', label: 'Journal', Icon: BookOpen }, { id: 'calendar', label: 'Calendar', Icon: CalendarDays }, { id: 'favorites', label: 'Favorites', Icon: Heart }].map(({ id, label, Icon }) => <button key={id} onClick={() => go(id)} className={view === id ? 'active' : ''}><Icon size={19} /><span>{label}</span></button>)}<button className="mobile-tab-new" onClick={() => setEditor({})}><span><Plus size={19} /></span><span>Write</span></button></nav>
    {editor && <EntryEditor entry={editor.id ? editor : null} onClose={() => setEditor(null)} onSave={saveEntry} />}{toast && <div className="toast"><span><Check size={16} /></span>{toast}</div>}
  </div>;
}

function EmptyState({ onCreate, message = 'Your first entry is waiting for you.' }) {
  return <div className="empty-state"><div className="empty-art"><Leaf size={43} /></div><h2>{message}</h2><p>Start with a small thought. There’s no right way to begin.</p><button className="btn btn-primary" onClick={onCreate}><Plus size={16} /> Write an entry</button></div>;
}

export default App;
