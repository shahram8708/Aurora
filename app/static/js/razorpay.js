export function openRazorpay(order, onSuccess) {
  const rzp = new Razorpay({
    key: window.RAZORPAY_KEY_ID || '',
    order_id: order.id,
    amount: order.amount,
    currency: order.currency || 'INR',
    name: order.notes?.purpose || 'Payment',
    prefill: order.prefill || {},
    notes: order.notes,
    handler: onSuccess,
    theme: { color: '#0d6efd' },
  });
  rzp.open();
}
