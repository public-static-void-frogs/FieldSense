export function getPagination(total: number, page: number, pageSize: number) {
  const currentPage = Math.min(page, Math.max(1, Math.ceil(total / pageSize)));
  return {
    currentPage,
    first: total ? (currentPage - 1) * pageSize + 1 : 0,
    last: Math.min(currentPage * pageSize, total),
  };
}
