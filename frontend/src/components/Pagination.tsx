import React from 'react';
import { ChevronLeft, ChevronRight, ChevronsLeft, ChevronsRight } from 'lucide-react';

interface PaginationProps {
  page: number;
  totalPages: number;
  onPageChange: (page: number) => void;
}

const Pagination: React.FC<PaginationProps> = ({ page, totalPages, onPageChange }) => {
  if (totalPages <= 1) return null;

  const getVisiblePages = (): (number | '...')[] => {
    const pages: (number | '...')[] = [];
    const delta = 2;
    const left = Math.max(2, page - delta);
    const right = Math.min(totalPages - 1, page + delta);

    pages.push(1);
    if (left > 2) pages.push('...');
    for (let i = left; i <= right; i++) pages.push(i);
    if (right < totalPages - 1) pages.push('...');
    if (totalPages > 1) pages.push(totalPages);

    return pages;
  };

  const btnBase =
    'flex items-center justify-center w-8 h-8 rounded-lg text-sm font-medium transition-all duration-150';
  const btnActive = 'bg-brand-600 text-white shadow-md shadow-brand-600/30';
  const btnInactive = 'text-gray-400 hover:bg-gray-700 hover:text-white';
  const btnDisabled = 'text-gray-600 cursor-not-allowed';

  return (
    <div className="flex items-center justify-center gap-1 mt-4">
      <button
        className={`${btnBase} ${page === 1 ? btnDisabled : btnInactive}`}
        onClick={() => onPageChange(1)}
        disabled={page === 1}
      >
        <ChevronsLeft className="w-4 h-4" />
      </button>
      <button
        className={`${btnBase} ${page === 1 ? btnDisabled : btnInactive}`}
        onClick={() => onPageChange(page - 1)}
        disabled={page === 1}
      >
        <ChevronLeft className="w-4 h-4" />
      </button>

      {getVisiblePages().map((p, i) =>
        p === '...' ? (
          <span key={`dots-${i}`} className="w-8 h-8 flex items-center justify-center text-gray-500">
            ...
          </span>
        ) : (
          <button
            key={p}
            className={`${btnBase} ${p === page ? btnActive : btnInactive}`}
            onClick={() => onPageChange(p)}
          >
            {p}
          </button>
        ),
      )}

      <button
        className={`${btnBase} ${page === totalPages ? btnDisabled : btnInactive}`}
        onClick={() => onPageChange(page + 1)}
        disabled={page === totalPages}
      >
        <ChevronRight className="w-4 h-4" />
      </button>
      <button
        className={`${btnBase} ${page === totalPages ? btnDisabled : btnInactive}`}
        onClick={() => onPageChange(totalPages)}
        disabled={page === totalPages}
      >
        <ChevronsRight className="w-4 h-4" />
      </button>
    </div>
  );
};

export default Pagination;
