import Image from 'next/image';

export function Logo({ className = '' }: { className?: string }) {
  return (
    <div className={`flex items-center gap-2 ${className}`}>
      {/* Logo - remplacez par votre logo dans /public/logo.png ou .svg */}
      <div className="w-10 h-10 bg-gradient-to-br from-primary-500 to-primary-700 rounded-lg flex items-center justify-center shadow-lg">
        <span className="text-white font-bold text-xl">V</span>
      </div>
      <span className="text-2xl font-bold bg-gradient-to-r from-primary-600 to-primary-800 bg-clip-text text-transparent">
        Vykso
      </span>
    </div>
  );
}
