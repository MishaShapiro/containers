# монтирование и смена корня
mount
umount2
pivot_root
# создание/вход в namespaces (основа многих побегов)
unshare
setns
# ядро, модули, перезагрузка
reboot
kexec_load
kexec_file_load
init_module
finit_module
delete_module
swapon
swapoff
# отладка и чтение чужой памяти
ptrace
process_vm_readv
process_vm_writev
# время системы
clock_settime
clock_adjtime
settimeofday
adjtimex
# прочие опасные интерфейсы ядра
bpf
perf_event_open
keyctl
add_key
request_key
open_by_handle_at
userfaultfd
acct
quotactl
